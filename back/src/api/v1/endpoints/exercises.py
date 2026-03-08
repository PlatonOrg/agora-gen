from fastapi import APIRouter, HTTPException, Depends
from redis.asyncio import Redis
import asyncio
import json
import logging
from typing import List, Dict, Any

from src.infra.db.redis import get_redis
from src.services.models.api import ExerciseData
from src.services.models.platon import PublishExerciseRequest, PublishExerciseResponse, PublishFile
from src.services.platon_service import platon_service
from src.services.workspace_service import workspace_service
from src.services.auth_service import auth_service
from src.api.v1.dependencies import require_session_id
from src.infra.log.db_logger import log_publish_event
from src.infra.log.models import PublishEventLog

logger = logging.getLogger("uvicorn")

router = APIRouter(
    prefix="/exercises",
    tags=["exercises"],
)


@router.get("/tags")
async def get_exercise_tags(
    session_id: str = Depends(require_session_id),
    redis: Redis = Depends(get_redis),
) -> Dict[str, List[Dict[str, Any]]]:
    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")
    user_token = session_data.get("platon_access")
    if not user_token:
        raise HTTPException(status_code=401, detail="No Platon access token")
    try:
        topics, levels = await asyncio.gather(
            platon_service.get_topics(token=user_token),
            platon_service.get_levels(token=user_token),
        )
        return {"topics": topics, "levels": levels}
    except Exception as e:
        logger.error(f"Failed to fetch tags: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch tags: {e}")


@router.post("/state/save/{exercise_id}", response_model=ExerciseData)
async def save_exercise_state(
    exercise_id: str,
    exercise_data: ExerciseData,
    redis: Redis = Depends(get_redis),
) -> ExerciseData:
    try:
        exercise_data.exercise_id = exercise_id
        workspace_service.sanitise_exercise_data(exercise_data)
        cache_key = f"exercise:{exercise_id}"
        await redis.setex(cache_key, 86400, exercise_data.model_dump_json())
        logger.info(f"Upserted exercise {exercise_id}")
        return exercise_data
    except Exception as e:
        logger.error(f"Failed to save exercise {exercise_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{exercise_id}", response_model=ExerciseData)
async def get_exercise_state(
    exercise_id: str,
    redis: Redis = Depends(get_redis),
) -> ExerciseData:
    try:
        cache_key = f"exercise:{exercise_id}"
        cached_data = await redis.get(cache_key)
        if not cached_data:
            raise HTTPException(status_code=404, detail=f"No cached state found for exercise '{exercise_id}'")
        logger.info(f"Retrieved exercise {exercise_id}")
        return ExerciseData(**json.loads(cached_data))
    except json.JSONDecodeError as e:
        logger.error(f"Invalid cached data for {exercise_id}: {e}")
        raise HTTPException(status_code=500, detail="Corrupted cache entry")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve exercise {exercise_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/state/{exercise_id}", response_model=ExerciseData)
async def clear_exercise_state(
    exercise_id: str,
    redis: Redis = Depends(get_redis),
) -> ExerciseData:
    try:
        cache_key = f"exercise:{exercise_id}"
        cached_data = await redis.get(cache_key)
        if not cached_data:
            raise HTTPException(status_code=404, detail=f"No cached state found for exercise '{exercise_id}'")
        exercise_data = ExerciseData(**json.loads(cached_data))
        await redis.delete(cache_key)
        logger.info(f"Deleted exercise {exercise_id}")
        return exercise_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete exercise {exercise_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _build_metadata_readme(exercise_data: ExerciseData) -> str:
    lines = []

    titre = exercise_data.titre or exercise_data.name
    if titre:
        lines.append(f"# {titre}")
        lines.append("")

    if exercise_data.description:
        lines.append("## Description")
        lines.append("")
        lines.append(exercise_data.description)
        lines.append("")

    readme_body = exercise_data.metadata.readme
    if readme_body:
        lines.append(readme_body)
        lines.append("")

    theories = exercise_data.theories or []
    if theories:
        lines.append("## Ressources")
        lines.append("")
        for theory in theories:
            title = theory.get("title", "")
            url = theory.get("url", "")
            if title and url:
                lines.append(f"- [{title}]({url})")
            elif title:
                lines.append(f"- {title}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _build_tags_md(exercise_data: ExerciseData) -> str:
    lines = []
    levels = exercise_data.metadata.levels or []
    topics = exercise_data.metadata.topics or []
    if levels:
        lines.append("Niveaux : " + ", ".join(levels))
    if topics:
        lines.append("Sujets : " + ", ".join(topics))
    return "\n".join(lines)


@router.post("/publish/{exercise_id}", response_model=PublishExerciseResponse)
async def publish_exercise(
    exercise_id: str,
    publish_request: PublishExerciseRequest,
    session_id: str = Depends(require_session_id),
    redis: Redis = Depends(get_redis),
) -> PublishExerciseResponse:

    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    user_token = session_data.get("platon_access")
    if not user_token:
        raise HTTPException(status_code=401, detail="No Platon access token")

    cache_key = f"exercise:{exercise_id}"
    cached_data = await redis.get(cache_key)
    if not cached_data:
        raise HTTPException(status_code=404, detail=f"Exercise '{exercise_id}' not found in cache")

    try:
        exercise_data = ExerciseData(**json.loads(cached_data))
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to deserialize exercise {exercise_id}: {e}")
        raise HTTPException(status_code=500, detail="Corrupted exercise data")

    readme_content = exercise_data.metadata.readme if exercise_data.metadata.readme is not None else _build_metadata_readme(exercise_data)
    tags_content = _build_tags_md(exercise_data)

    level_names = exercise_data.metadata.levels or []
    topic_names = exercise_data.metadata.topics or []

    if level_names or topic_names:
        try:
            all_topics, all_levels = await asyncio.gather(
                platon_service.get_topics(token=user_token),
                platon_service.get_levels(token=user_token),
            )
            topic_name_to_id = {t["name"]: t["id"] for t in all_topics if "name" in t and "id" in t}
            level_name_to_id = {l["name"]: l["id"] for l in all_levels if "name" in l and "id" in l}
            publish_request.topics = [topic_name_to_id[n] for n in topic_names if n in topic_name_to_id]
            publish_request.levels = [level_name_to_id[n] for n in level_names if n in level_name_to_id]
        except Exception as e:
            logger.warning(f"Could not resolve tag names to IDs for exercise {exercise_id}: {e}")
            publish_request.topics = []
            publish_request.levels = []
    else:
        publish_request.topics = []
        publish_request.levels = []

    if not exercise_data.template_id:
        workspace_service.sanitise_exercise_data(exercise_data)
        ple_content = workspace_service.from_json_to_ple(exercise_data)
        files = [PublishFile(path="main.ple", content=ple_content)]
        if readme_content:
            files.append(PublishFile(path="readme.md", content=readme_content))
        if tags_content:
            files.append(PublishFile(path="tags.md", content=tags_content))
        publish_request.files = files
    else:
        ple_content = f"@extends /{exercise_data.template_id}:latest/main.ple"
        plo_content = json.dumps(exercise_data.config_variables)
        publish_request.templateId = exercise_data.template_id
        publish_request.templateVersion = "latest"
        files = [
            PublishFile(path="main.ple", content=ple_content),
            PublishFile(path="main.plo", content=plo_content),
        ]
        if readme_content:
            files.append(PublishFile(path="readme.md", content=readme_content))
        if tags_content:
            files.append(PublishFile(path="tags.md", content=tags_content))
        publish_request.files = files

    try:
        response = await platon_service.publish_exercise(publish_request, token=user_token)
        logger.info(f"Published exercise {exercise_id} to Platon as {response.id}")
        # Fire-and-forget async call to log publish event
        asyncio.ensure_future(log_publish_event(PublishEventLog(
            exercise_id=exercise_id,
            platon_resource_id=response.id,
            session_id=session_id,
            username=session_data.get("username"),
            template_id=exercise_data.template_id,
        )))
        return response
    except Exception as e:
        logger.error(f"Failed to publish exercise {exercise_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Platon publish failed: {e}")

