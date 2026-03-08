from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore

from src.infra.llm.llm_wrapper import chat_text_with_llm
from src.infra.log.db_logger import log_discussion_generation
from src.infra.log.models import DiscussionGenerationLog
from src.services.models.api import PlatonDocsSource
from src.services.models.rag import RetrievedChunk
from src.core import path_constants

logger = logging.getLogger("uvicorn")


@dataclass(frozen=True)
class _PlatonDocsConfig:
    """Immutable snapshot of infrastructure settings needed by Platon docs QA."""
    embed_model: str
    qa_enabled: bool
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    vector_table: str


def _load_platon_docs_config() -> _PlatonDocsConfig:
    from src.core.config_app import settings
    from src.core import path_constants
    return _PlatonDocsConfig(
        embed_model=str(path_constants.PLATON_DOCS_EMBED_MODEL),
        qa_enabled=settings.PLATON_DOCS_QA_ENABLED,
        db_host=settings.POSTGRES_HOST,
        db_port=settings.POSTGRES_PORT,
        db_user=settings.POSTGRES_USER,
        db_password=settings.POSTGRES_PASSWORD,
        db_name=settings.POSTGRES_DB,
        vector_table=settings.PLATON_DOCS_VECTOR_TABLE,
    )


_cfg = _load_platon_docs_config()

_PLATON_DOCS_INDEX: Optional[VectorStoreIndex] = None
_PLATON_DOCS_EMBED_MODEL: Optional[HuggingFaceEmbedding] = None
_PLATON_DOCS_EMBED_DIM: Optional[int] = None
_PLATON_DOCS_INIT_ERROR: Optional[str] = None


def get_platon_docs_embed_model() -> HuggingFaceEmbedding:
    global _PLATON_DOCS_EMBED_MODEL
    if _PLATON_DOCS_EMBED_MODEL is None:
        model_ref = _cfg.embed_model
        logger.info("Loading Platon docs embedding model: %s", model_ref)
        _PLATON_DOCS_EMBED_MODEL = HuggingFaceEmbedding(model_name=model_ref, normalize=True)
    return _PLATON_DOCS_EMBED_MODEL


def get_platon_docs_embed_dim() -> int:
    global _PLATON_DOCS_EMBED_DIM
    if _PLATON_DOCS_EMBED_DIM is None:
        embed_model = get_platon_docs_embed_model()
        probe = embed_model.get_text_embedding("probe")
        _PLATON_DOCS_EMBED_DIM = len(probe)
        logger.info("Platon docs embedding dimension probed: %d", _PLATON_DOCS_EMBED_DIM)
    return _PLATON_DOCS_EMBED_DIM


def initialize_platon_docs_qa_service() -> bool:
    global _PLATON_DOCS_INDEX, _PLATON_DOCS_INIT_ERROR
    logger.info("Initializing Platon docs QA service...")

    if not _cfg.qa_enabled:
        _PLATON_DOCS_INIT_ERROR = "Platon docs QA service disabled by configuration."
        logger.warning(_PLATON_DOCS_INIT_ERROR)
        return False

    try:
        embed_dim = get_platon_docs_embed_dim()

        vector_store = PGVectorStore.from_params(
            database=_cfg.db_name,
            host=_cfg.db_host,
            password=_cfg.db_password,
            port=_cfg.db_port,
            user=_cfg.db_user,
            table_name=_cfg.vector_table,
            embed_dim=embed_dim,
        )

        _PLATON_DOCS_INDEX = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=get_platon_docs_embed_model(),
        )
        _PLATON_DOCS_INIT_ERROR = None
        logger.info("Platon docs QA service initialized (model=%s, dim=%d).", _cfg.embed_model, embed_dim)
        return True
    except Exception as exc:
        _PLATON_DOCS_INDEX = None
        _PLATON_DOCS_INIT_ERROR = (
            f"Platon docs QA init failed. Check PLATON_DOCS_EMBED_MODEL and PLATON_DOCS_VECTOR_TABLE. "
            f"Root error: {exc}"
        )
        logger.warning(_PLATON_DOCS_INIT_ERROR)
        return False


def get_platon_docs_index() -> VectorStoreIndex:
    if _PLATON_DOCS_INDEX is None:
        detail = _PLATON_DOCS_INIT_ERROR or "Platon docs QA service is not initialized."
        raise RuntimeError(detail)
    return _PLATON_DOCS_INDEX


def get_platon_docs_init_error() -> Optional[str]:
    return _PLATON_DOCS_INIT_ERROR


class PlatonDocsQAService:
    @staticmethod
    def _score_value(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    @staticmethod
    def _normalize_text(value: str) -> str:
        raw = (value or "").strip().lower()
        ascii_like = "".join(
            ch for ch in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(ch)
        )
        return re.sub(r"\s+", " ", ascii_like)

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        return {t for t in re.findall(r"[a-zA-Z0-9]{3,}", (value or "").lower())}

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        """Best-effort integer conversion for inconsistent metadata values."""
        if value is None:
            return default
        try:
            raw = str(value).strip()
            if not raw or raw.lower() == "none":
                return default
            return int(float(raw))
        except (TypeError, ValueError):
            return default

    async def _build_query_variants(self, query: str) -> list[str]:
        """Use the LLM to rewrite query variants (typo tolerant, multilingual)."""
        base = query.strip()
        normalized = self._normalize_text(base)
        variants: list[str] = []
        if base:
            variants.append(base)
        if normalized and normalized not in variants:
            variants.append(normalized)

        prompt = (
            "Generate up to 4 search query variants for document retrieval.\n"
            "Goals:\n"
            "- preserve intent\n"
            "- correct typos if present\n"
            "- support mixed-language phrasing\n"
            "- keep queries concise\n"
            "Return one variant per line, no numbering, no explanations.\n\n"
            f"User query:\n{base}"
        )
        try:
            rewritten = await chat_text_with_llm(
                system_prompt="You generate robust multilingual search rewrites.",
                user_request=prompt,
                temperature=0.0,
            )
            for line in rewritten.text.splitlines():
                cleaned = line.strip(" -\t\r\n")
                if not cleaned:
                    continue
                if cleaned not in variants:
                    variants.append(cleaned)
        except Exception:
            pass
        return variants[:6]

    def _is_low_signal_chunk(self, text: str) -> bool:
        return not (text or "").strip()

    def _closest_fallback_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return (
                "Je n'ai pas trouve une correspondance directe, mais voici l'orientation la plus proche: "
                "consultez la section la plus pertinente de la documentation PLaTon via les sources associees."
            )
        top = chunks[0]
        src = str(top.metadata.get("source_path", "unknown"))
        excerpt = re.sub(r"\s+", " ", (top.content or "").strip())
        excerpt = excerpt[:500]
        return (
            "Je n'ai pas trouve une correspondance exacte; voici la reponse la plus proche selon la documentation: "
            f"{excerpt} (source: {src})."
        )

    def _retrieve_docs_chunks_vector(self, *, query: str, top_k: int) -> list[RetrievedChunk]:
        index = get_platon_docs_index()
        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)

        out: list[RetrievedChunk] = []
        for n in nodes:
            md = dict(getattr(n.node, "metadata", {}) or {})
            content = n.node.get_content()
            if self._is_low_signal_chunk(content):
                continue
            out.append(
                RetrievedChunk(
                    doc_type="platon_docs",
                    name=md.get("source_path"),
                    score=getattr(n, "score", None),
                    content=content,
                    metadata=md,
                )
            )
        return out

    def retrieve_docs_chunks(self, *, queries: list[str], top_k: int) -> list[RetrievedChunk]:
        candidate_k = max(top_k * 4, 10)

        vector_chunks: list[RetrievedChunk] = []
        for qv in queries:
            vector_chunks.extend(self._retrieve_docs_chunks_vector(query=qv, top_k=candidate_k))
        query_tokens = self._tokenize(" ".join(queries))

        merged: list[tuple[float, RetrievedChunk]] = []
        seen: set[tuple[str, int]] = set()

        for chunk in vector_chunks:
            source_path = str(chunk.metadata.get("source_path", "unknown"))
            chunk_index = self._to_int(chunk.metadata.get("chunk_index", 0))
            key = (source_path, chunk_index)
            if key in seen:
                continue
            seen.add(key)
            overlap = 0.0
            if query_tokens:
                overlap = len(query_tokens & self._tokenize(chunk.content)) / float(len(query_tokens))
            vector_score = float(chunk.score or 0.0)
            blended = (1.0 * vector_score) + (1.5 * overlap)
            merged.append((blended, chunk))

        merged.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in merged[:top_k]]

    async def answer_question(self, *, question: str, top_k: int | None = None, session_id: str | None = None, conversation_id: str | None = None, username: str | None = None) -> tuple[str, list[PlatonDocsSource]]:
        from src.services.runtime_config_service import runtime_config, SettingKey
        requested_top_k = top_k if top_k is not None else runtime_config.get_int(SettingKey.PLATON_DOCS_TOP_K)
        use_top_k = min(max(int(requested_top_k), 1), 10)
        variants = await self._build_query_variants(question)
        chunks = self.retrieve_docs_chunks(queries=variants, top_k=use_top_k)

        if not chunks:
            # Broad semantic retry to avoid empty responses on sparse lexical overlap.
            broad_variants = list(dict.fromkeys([question, self._normalize_text(question)] + variants))
            chunks = self.retrieve_docs_chunks(
                queries=[q for q in broad_variants if q],
                top_k=max(10, use_top_k * 2),
            )
            if not chunks:
                return (self._closest_fallback_answer(question, []), [])

        chunks_by_score = sorted(
            chunks,
            key=lambda c: self._score_value(c.score),
            reverse=True,
        )[:10]

        sources: list[PlatonDocsSource] = []
        context_lines: list[str] = []
        for chunk in chunks_by_score:
            source_path = str(chunk.metadata.get("source_path", "unknown"))
            chunk_index = self._to_int(chunk.metadata.get("chunk_index", 0))
            excerpt = chunk.content.strip()
            sources.append(
                PlatonDocsSource(
                    source_path=source_path,
                    chunk_index=chunk_index,
                    score=chunk.score,
                    excerpt=excerpt[:400],
                )
            )
            context_lines.append(f"[{source_path}#chunk-{chunk_index}]\n{excerpt}")

        system_prompt_path = path_constants.PROMPTS_DIR / "platon_docs_qa.txt"
        system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()
        user_prompt = (
            f"Question utilisateur:\n{question}\n\n"
            f"Contexte documentation:\n\n" + "\n\n".join(context_lines)
        )

        llm_result = await chat_text_with_llm(
            system_prompt=system_prompt,
            user_request=user_prompt,
            temperature=0.1,
        )
        answer = llm_result.text or self._closest_fallback_answer(question, chunks)

        embed_model = _PLATON_DOCS_EMBED_MODEL
        embed_model_name = getattr(embed_model, "model_name", _cfg.embed_model)
        asyncio.ensure_future(log_discussion_generation(DiscussionGenerationLog(
            user_request=question,
            retrieved_chunks=chunks_by_score,
            embedding_model=embed_model_name,
            vector_table=_cfg.vector_table,
            rag_query=question,
            system_prompt_name="platon_docs_qa",
            llm_raw_output=llm_result.raw_text or None,
            llm_output=answer,
            llm_provider=llm_result.provider,
            llm_model=llm_result.model,
            session_id=session_id,
            conversation_id=conversation_id,
            username=username,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
        )))

        return answer, sources


platon_docs_qa_service = PlatonDocsQAService()

