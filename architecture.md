# Architecture Technique — Agora AI Agent

## Vue d'ensemble

Agora est une application fullstack permettant à des enseignants de générer des exercices PLaTon à l'aide d'un agent IA conversationnel. L'application combine RAG (Retrieval-Augmented Generation), des LLM multi-fournisseurs, et une intégration profonde avec la plateforme PLaTon.

---

## Infrastructure

### Environnements

| Environnement | Fichier de config | Description |
|---|---|---|
| Développement | `docker-compose.yml` | Avec hot-reload, volumes montés, Ollama local |
| Production | `docker-compose.prod.yml` | Images Docker pré-buildées depuis GHCR, sans Ollama |

### Services Docker

```
┌─────────────────────────────────────────────────────────────────┐
│                         Réseau: agora_net                        │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Frontend   │    │   Backend    │    │   Ollama (dev)   │   │
│  │  (Nginx:80)  │───▶│ (FastAPI:   │───▶│  (LLM local:    │   │
│  │  Angular SSR │    │  8000)      │    │   11434)         │   │
│  └──────────────┘    └──────┬───┬──┘    └──────────────────┘   │
│                             │   │                                │
│                    ┌────────┘   └────────┐                       │
│                    ▼                     ▼                       │
│  ┌──────────────────────┐   ┌──────────────────────┐            │
│  │  PostgreSQL + pgvector│   │       Redis          │            │
│  │  (port 5433 en dev)   │   │  (sessions, cache,  │            │
│  │  Vecteurs RAG         │   │   files, stop-flag) │            │
│  └──────────────────────┘   └──────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### Nginx (Frontend)

- Sert l'application Angular compilée
- Proxy `/api/` → `agora_backend:8000`
- Configuration SSE : `gzip off`, `proxy_buffering off`, `X-Accel-Buffering: no`
- Headers proxy : `X-Forwarded-Proto`, `X-Real-IP`, `X-Forwarded-For`

---

## Backend (FastAPI / Python 3.11)

### Structure des fichiers

```
back/src/
├── main.py                      # Point d'entrée FastAPI, lifespan, middlewares
├── api/
│   └── v1/
│       ├── api.py               # Agrégation des routers
│       ├── schemas.py           # Schémas Pydantic partagés (auth, context)
│       └── endpoints/
│           ├── auth.py          # OAuth PLaTon (init, callback, user, logout)
│           ├── chat.py          # SSE streaming, upload fichiers, stop génération
│           ├── context.py       # Cercles, topics, levels, templates, preview PLE
│           ├── exercises.py     # Tags, save/load état exercice, publication
│           ├── logs.py          # Consultation des logs de génération
│           └── platon_docs_qa.py # Q&A documentation PLaTon
├── core/
│   ├── config_app.py            # Settings centralisé (pydantic-settings, .env)
│   ├── di.py                    # Registre LLM (LLMProviderRegistry)
│   ├── logging_config.py        # Loggers rotatifs par fichier
│   ├── path_constants.py        # Chemins absolus (prompts, modèles, etc.)
│   └── sqlalchemy.py            # Engine asyncpg, session factory
├── infra/
│   ├── db/
│   │   ├── database.py          # Init PostgreSQL + pgvector
│   │   ├── redis.py             # Pool Redis asyncio
│   │   ├── components_repo.py   # Requêtes SQL composants
│   │   ├── templates_repo.py    # Requêtes SQL templates
│   │   └── template_uses_repo.py
│   ├── llm/
│   │   ├── llm.py               # Protocol LLMProvider + LLMProviderRegistry
│   │   ├── providers.py         # Implémentations : OpenAI-compatible, Gemini, Ollama, Ragustave
│   │   ├── llm_wrapper.py       # Façade applicative (chat_with_llm, chat_text_with_llm)
│   │   ├── json_facility.py     # Construction des JSON Schemas pour structured output
│   │   ├── llm_call_logger.py   # Logs des appels LLM (fichiers JSON)
│   │   └── file_upload_logger.py
│   ├── files/
│   │   ├── file_content_service.py  # Stockage Redis du texte extrait + résumés
│   │   ├── file_summarizer.py       # Résumé LLM des fichiers joints
│   │   ├── parsers.py               # Extraction texte (PDF, DOCX, TXT…)
│   │   ├── truncation.py            # Troncature par tokens
│   │   └── models.py                # FileSummaryResult
│   └── log/
│       ├── db_logger.py         # Persistance des logs de génération en DB
│       └── models.py            # Modèles SQLAlchemy (ExoGeneration, DiscussionGeneration…)
├── services/
│   ├── auth_service.py          # OAuth state, sessions Redis, JWT decode
│   ├── platon_service.py        # Client HTTP PLaTon API (httpx async)
│   ├── workspace_service.py     # Sanitisation ExerciseData, formatage PLE/PLO
│   ├── generation_service.py    # Génération LLM exercices purs et templates
│   ├── component_selection_service.py  # Sélection LLM des composants PLaTon
│   ├── sandbox_correction_service.py   # Boucle correction sandbox (retry loop)
│   ├── template_service.py      # Filtrage templates (Platon API + DB locale)
│   ├── logs_service.py          # Lecture et formatage des logs
│   ├── rag/
│   │   ├── retrieval_service.py     # Index LlamaIndex, BM25 + dense fusion, reranking
│   │   ├── platon_docs_qa_service.py # Q&A sur la documentation PLaTon
│   │   ├── embedding_types.py       # Enum EmbeddingKind (EXERCICE, TEMPLATE, COMPONENT…)
│   │   └── filters.py               # Filtres par kind pour la recherche vectorielle
│   └── models/
│       ├── api.py               # ExerciseData, ChatRequest, ChatResponse, TemplateResponse…
│       ├── platon.py            # SandboxError, PreviewResult, PublishExerciseRequest…
│       ├── rag.py               # RetrievedChunk
│       ├── schemas.py           # TYPE_MAP (types variables → JSON Schema)
│       └── logs.py              # SessionSummary, RagSearchInfo, ComponentSelectionLog…
└── workflows/
    ├── workflow.py              # Orchestrateur principal (handle_chat, generate_and_process_template)
    └── retry_handler.py         # Boucle retry générique avec timeout asyncio
```

### Couches applicatives

```
Requête HTTP
     │
     ▼
┌──────────────────────────────────────────────┐
│             API Layer (FastAPI)               │
│  Routing, Auth guards, SSE, File upload       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│           Workflow Layer                      │
│  handle_chat → orchestre le flux complet      │
│  Emit progress events (SSE) via callback      │
└──────────────────────┬───────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌──────────────┐ ┌──────────┐ ┌──────────────────┐
│   Services   │ │   RAG    │ │  LLM Infra       │
│ generation   │ │ retrieve │ │ providers.py     │
│ component    │ │ rerank   │ │ json_facility.py │
│ sandbox      │ │ BM25+    │ │ llm_wrapper.py   │
│ correction   │ │ dense    │ │                  │
└──────┬───────┘ └────┬─────┘ └──────────────────┘
       │              │
       ▼              ▼
┌──────────────────────────────────────────────┐
│          Infrastructure Layer                 │
│  PostgreSQL+pgvector  Redis  PLaTon API       │
└──────────────────────────────────────────────┘
```

### Flux de génération SSE

```
Client                      API /chat/          Workflow         Services
  │                              │                  │                │
  │─── POST /api/v1/chat/ ──────▶│                  │                │
  │                              │─── create_task ─▶│                │
  │◀── event: generation_started │                  │                │
  │                              │                  │── RAG search ─▶│
  │◀── event: retrieval_started  │◀─ progress cb ──│                │
  │◀── event: retrieval_completed│◀─ progress cb ──│                │
  │                              │                  │── LLM call ───▶│
  │◀── event: llm_generation_*   │◀─ progress cb ──│                │
  │                              │                  │── Sandbox ────▶│
  │◀── event: preview_started    │◀─ progress cb ──│                │
  │◀── event: complete           │◀─── task done ──│                │
  │                              │                  │                │
  │─── POST /api/v1/chat/stop ──▶│ (annulation)     │                │
```

### Authentification

```
1. GET  /api/v1/auth/platon/init    → génère state Redis, retourne redirectUrl PLaTon
2. [Redirect PLaTon] → Frontend /auth/callback avec token JWT
3. POST /api/v1/auth/platon/callback → valide state, decode JWT, crée session Redis (24h)
4. Cookie `agora_session_id` → session Redis → token PLaTon pour appels API
```

### LLM Providers

| Provider | Classe | Configuration |
|---|---|---|
| OpenAI-compatible | `OpenAICompatibleProvider` | `base_url`, `api_key`, `model` |
| Groq | Instance OpenAI-compatible | Via `llm_providers.json` |
| Gemini | `GeminiProvider` | `api_key`, via `google-genai` |
| Ollama | `OllamaProvider` | `base_url` local |
| Ragustave | `RagustaveProvider` | Compatible OpenAI, supporte upload fichiers |
| OpenRouter | `OpenRouterProvider` | `api_key`, retry automatique |
| Cerebras | `CerebrasProvider` | `api_key`, SDK synchrone |

Configuration dans `resources/llm_providers.json`. L'entrée avec `"default": true` est le fournisseur actif. Modifiable à chaud via `PUT /admin/llm-config` (admin). Registry dans `core/di.py`.

### RAG Pipeline

```
Query
  │
  ├── HuggingFace Embedding (multilingual-e5-large-instruct)
  │
  ├── Dense Vector Search (pgvector via LlamaIndex)
  │
  ├── BM25 Lexical Search (llama-index-retrievers-bm25)
  │
  ├── QueryFusionRetriever (fusion dense + BM25)
  │
  └── SentenceTransformerRerank (top-N reranking)
       │
       └── RetrievedChunk[] → Workflow
```

Deux index distincts :
- **agora_rag_embeddings** : exercices, templates, composants PLaTon
- **platon_docs_fr_chunks** : documentation PLaTon (pour Q&A)

### JSON Schema & Structured Output

`json_facility.py` construit les schémas JSON Schema bruts :
- `build_fixed_exercise_json_schema()` : schéma complet d'exercice pur (name, description, title, sandbox, builder, grader, statement, form, solution, hint, theories, levels, topics)
- `build_json_schema_from_config()` : schéma dynamique depuis la config template (inputs[])
- `build_component_selection_schema()` : schéma pour la sélection de composants

Chaque provider implémente `wrap_json_schema()` pour envelopper selon son format (Gemini, OpenAI response_format, etc.).

---

## Frontend (Angular 19 + SSR)

### Structure des fichiers

```
front/src/app/
├── app.routes.ts                # Routes : /login, /auth/callback, /workspace, /logs
├── app.config.ts                # Configuration Angular (providers, router)
├── core/
│   ├── api/
│   │   └── api.service.ts       # Service HTTP générique (GET, POST, credentials)
│   ├── auth/
│   │   ├── auth.service.ts      # État auth (signal), init, callback, logout
│   │   ├── user-profile.service.ts
│   │   └── user.model.ts
│   ├── llm/
│   │   └── llm-capabilities.service.ts  # File support, uploaded files
│   └── logging/
├── features/
│   ├── auth/
│   │   └── components/
│   │       ├── authentication-page.component.ts   # Page de login PLaTon
│   │       └── auth-callback.component.ts          # Traitement callback OAuth
│   ├── logging/
│   │   └── components/
│   │       └── logging-page/    # Visualisation des logs de génération
│   └── workspace/
│       ├── models/
│       │   ├── exercise.model.ts    # ExerciseData, ChatRequest, ChatResponse, ComponentInstance
│       │   ├── template.model.ts    # FilterTemplatesRequest, TemplateResponse
│       │   └── publish.model.ts     # PublishExerciseRequest
│       ├── services/
│       │   ├── chat.service.ts              # SSE streaming, EventSource, AbortController
│       │   ├── context.service.ts           # Cercles, topics, levels, templates (API)
│       │   ├── exercise.service.ts          # Save/load état exercice (Redis backend)
│       │   ├── components-metadata.service.ts  # Métadonnées composants PLaTon
│       │   └── file-validation.service.ts
│       ├── state/
│       │   ├── workspace.store.ts           # Signaux UI (panels, tabs, composants)
│       │   ├── workspace.facade.ts          # Coordination init workspace
│       │   ├── workspace-template.service.ts # Build ExerciseData depuis template
│       │   ├── workspace-filters.store.ts   # Filtres templates (cercle, sujets, niveaux)
│       │   └── workspace-autosave.service.ts # Autosave périodique
│       └── components/
│           ├── workspace-page/      # Layout principal, resize panels
│           ├── workspace-header/    # Header avec profil utilisateur
│           ├── discussion/          # Panel conversation + génération SSE
│           │   ├── discussion-panel.component.*
│           │   ├── discussion.models.ts     # Message, GenerationTimelineData, GenerationStep
│           │   ├── discussion.cache.ts      # Persistance messages localStorage
│           │   ├── generation-timeline.ts   # Classe GenerationTimeline (états, détails)
│           │   ├── generation-steps/        # Composant affichage timeline
│           │   ├── message-bubble/          # Bulles de messages
│           │   ├── chat-input/              # Input avec badges composants/champs
│           │   └── attachment-badges/       # Badges fichiers attachés
│           ├── exercise-content/    # Éditeur contenu exercice (onglets)
│           │   ├── exercise-content-panel.component.*
│           │   ├── publish-dialog.component.ts
│           │   └── exercise-content.constants.ts
│           ├── components-panel/    # Panel composants PLaTon (formulaire + widgets)
│           ├── templates-panel/     # Recherche et sélection de templates
│           ├── template-parameters/ # Formulaire paramètres template
│           └── side-panel/          # Panel droit (composants + templates)
└── shared/
    ├── pipes/
    └── ui/
        ├── agora-logo/
        ├── component-tooltip/       # Tooltip composants (charcoal, arrow)
        ├── confirm-dialog/          # Dialog de confirmation
        ├── panel-header/            # En-têtes de panels réutilisables
        └── tree-select/             # Sélecteur arborescent (cercles PLaTon)
```

### Architecture des signaux (Angular Signals)

```
WorkspaceStore (signaux UI globaux)
  ├── activeLeftTab: 'discussion' | 'templates' | null
  ├── leftPanelWidth / rightPanelWidth
  ├── isComponentsPanelCollapsed
  ├── formulaireComponents / widgetComponents
  └── tooltipOpenFor

WorkspaceFiltersStore (filtres recherche templates)
  ├── selectedCircle
  ├── selectedTopics / selectedLevels / selectedComponents
  └── searchQuery

ExerciseService
  └── exerciseData: signal<ExerciseData>  (source de vérité unique)

ChatService
  ├── isGenerating: signal<boolean>
  ├── currentSteps: signal<GenerationStep[]>
  └── currentAbortController  (pour stop génération)
```

### Flux SSE côté frontend

```
ChatService
  └── sendMessage()
       ├── fetch POST /api/v1/chat/ (avec EventSource ou fetch stream)
       ├── parse "event: xxx\ndata: {...}\n\n"
       └── dispatch → GenerationTimeline
            ├── retrieval_started / completed → step 'analysis'
            ├── generation_mode              → détail mode
            ├── llm_generation_started       → step 'generation'
            ├── llm_generation_completed     → détail keys générées
            ├── preview_started / completed  → step 'sandbox'
            └── complete → exerciseData mis à jour via ExerciseService
```

### Gestion des états exercice

```
ExerciseData (signal)
     │
     ├── Mode Exercice pur
     │     └── fields: titre, enonce, forme, solution, sandbox,
     │                 construction, evaluation, indications, theories,
     │                 components, component_instances, levels, topics
     │
     └── Mode Template
           └── config_variables (inputs[])
               sandbox_variables (clé→valeur)
               template_id
               levels, topics (hérités du template)
```

---

## Modèles de données clés

### ExerciseData (Backend & Frontend)

| Champ | Type | Description |
|---|---|---|
| name | string | Nom de l'exercice |
| description | string | Description |
| titre | string | Titre affiché |
| enonce | string | Énoncé (HTML/Markdown) |
| forme | string | Formulaire (HTML PLaTon) |
| solution | string | Correction |
| indications | string[] | Indices |
| theories | {title, url}[] | Références théoriques |
| sandbox | 'node' \| 'python' | Type sandbox |
| construction | string | Script builder |
| evaluation | string | Script grader |
| template_id | string? | ID template PLaTon |
| config_variables | object | Config template (inputs[]) |
| sandbox_variables | object | Variables sandbox |
| component_instances | ComponentInstance[] | Instances de composants |
| levels | string[] | Niveaux (Licence 1, etc.) |
| topics | string[] | Sujets (Informatique, C, etc.) |
| exercise_id | string? | ID exercice PLaTon après preview |

### Publication (PublishExerciseRequest)

```json
{
  "name": "...",
  "parentId": "circle_id",
  "templateId": null,
  "desc": "...",
  "type": "EXERCISE",
  "status": "READY | DRAFT | BUGGED",
  "levels": ["uuid1", "uuid2"],
  "topics": ["uuid3"],
  "files": [
    { "path": "main.ple", "content": "..." },
    { "path": "readme.md", "content": "Niveaux: ...\nSujets: ..." }
  ]
}
```

---

## Base de données PostgreSQL

### Tables applicatives

| Table | Description |
|---|---|
| `component` | Composants PLaTon (tag, name, description, usage, category) |
| `template` | Templates PLaTon cachés (platon_id, variables JSONB) |
| `template_component_link` | Liaison N:N template ↔ composant |
| `agora_rag_embeddings` | Vecteurs RAG exercices/templates/composants (pgvector) |
| `platon_docs_fr_chunks` | Vecteurs documentation PLaTon (pgvector) |

### Tables de logs

| Table | Description |
|---|---|
| `log_prompt` | Prompts système versionnés |
| `exo_generation` | Sessions de génération d'exercice |
| `exo_generation_request` | Paramètres de la requête |
| `exo_generation_result` | Résultat (URL preview, retry) |
| `exo_rag_search` | Recherche RAG effectuée |
| `log_component_selection` | Sélection LLM des composants |
| `discussion_generation` | Sessions de génération Q&A docs |

### Redis (clés)

| Préfixe | TTL | Contenu |
|---|---|---|
| `session:{id}` | 24h | Profil utilisateur + tokens PLaTon |
| `oauth_state:{state}` | 10min | Flag validité state OAuth |
| `session_files:{id}` | 24h | Liste des fichiers uploadés |
| `file_content:{file_id}` | 24h | Texte extrait du fichier |
| `file_summary:{file_id}` | 24h | Résumé LLM du fichier |
| `generation_stop:{session_id}` | 30s | Flag d'annulation génération |

---

## Intégration PLaTon

### Endpoints PLaTon utilisés

| Endpoint | Usage |
|---|---|
| `GET /resources/{id}` | Info ressource (template/exercice) |
| `POST /resources/{id}/compile` | Compilation → variables résolues |
| `GET /resources/{id}/files/{filename}` | Lecture fichier (ex: main.plc) |
| `POST /resources/preview` | Prévisualisation sandbox |
| `POST /resources` | Création exercice (publication) |
| `GET /members/topics` | Liste des topics PLaTon |
| `GET /members/levels` | Liste des niveaux PLaTon |
| `GET /resources?filters=...` | Recherche templates filtrée |
| `GET /me` | Profil utilisateur connecté |

### Types de ressources PLaTon

| Type | Description |
|---|---|
| `EXERCISE` | Exercice pur PLaTon (`.ple`) |
| `TEMPLATE_EXO` | Exercice utilisant un template (`.plo`) |
| `TEMPLATE` | Template réutilisable (`.plc` config) |

---

## Flux complet de génération

```
1. Utilisateur saisit une demande dans le panel Discussion
        │
2. ChatService → POST /api/v1/chat/ (SSE)
        │
3. Backend auth via cookie → user_token PLaTon
        │
4. handle_chat() — Workflow principal
        │
   ┌────┴──────────────────────────────────────────────┐
   │                                                    │
   │  [Mode template direct]     [Mode découverte RAG]  │
   │  config_variables présentes  │                     │
   │         │                    ▼                     │
   │         │         RAG Search (pgvector + BM25)     │
   │         │              │                           │
   │         │         Reranking (SentenceTransformer)  │
   │         │              │                           │
   │         │         Best template trouvé ?           │
   │         │         ┌──Yes──┐        ┌──No──┐        │
   │         │         ▼       │        ▼      │        │
   │         │   Load template │   Component   │        │
   │         │   (main.plc)    │   Selection   │        │
   │         │         │       │   (LLM)       │        │
   │         ▼         ▼       │        ▼      │        │
   │   LLM génère config_vars  │   LLM génère  │        │
   │   (GenerationService)     │   exercice pur│        │
   │         │                 │   complet     │        │
   │         └───────────┬─────┘       │       │        │
   │                     ▼             ▼       │        │
   │               Platon Sandbox Preview      │        │
   │               (compile + prévisualisation)│        │
   │                     │                     │        │
   │               Erreur de sandbox ?         │        │
   │               → SandboxCorrectionService  │        │
   │               → Retry (max 3 fois)        │        │
   │                     │                     │        │
   └─────────────────────┼─────────────────────┘        │
                         ▼                              │
               event: complete → ExerciseData mis à jour
                         │
5. Frontend met à jour ExerciseData (signal)
        │
6. Utilisateur édite/publie → POST /api/v1/exercises/publish
```

---

## Sécurité

| Mécanisme | Description |
|---|---|
| Sessions Redis | Pas de JWT stocké côté client, cookie HttpOnly |
| OAuth state | Token CSRF Redis (10min TTL) |
| ProxyHeadersMiddleware | Respect X-Forwarded-Proto derrière Nginx SSL |
| CORS | Liste explicite d'origines autorisées |
| Validation Pydantic | Toutes les entrées API validées par schémas |
| Troncature fichiers | Limite `FILE_CONTENT_MAX_TOKENS` pour éviter injection prompt |

---

## Variables d'environnement clés (.env)

```env
# Database
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT

# Redis
REDIS_HOST, REDIS_PORT

# Auth
SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, SESSION_COOKIE_SECURE
PLATON_BASE_URL, PLATON_LOGIN_BASE_URL, PLATON_CALLBACK_URL
PLATON_PUBLIC_KEY, PLATON_API_TOKEN

# LLM
LLM_PROVIDERS_FILE    # Chemin vers resources/llm_providers.json
LLM_PROVIDERS         # JSON array (fallback si fichier absent)
TEMP_GENERATION       # Température LLM (0.0 par défaut)

# RAG
EMBED_DIM             # Dimension vecteurs (1024)
RAG_TABLE_NAME        # Table pgvector principale
PLATON_DOCS_EMBED_MODEL  # Chemin modèle embedding docs
NUM_EXAMPLE_EXERCISES    # Nb exemples injectés dans prompt (10)

# Sandbox
SANDBOX_RETRY_MAX_ATTEMPTS   # Max tentatives correction (3)
SANDBOX_RETRY_TIMEOUT_SECONDS

# Thresholds
TEMPLATE_SCORE_THRESHOLD     # Score min pour sélection template (0.9)
```

---

## Dépendances principales

### Backend

| Librairie | Rôle |
|---|---|
| `fastapi` | Framework API async |
| `uvicorn[standard]` | Serveur ASGI |
| `pydantic-settings` | Configuration typée |
| `sqlalchemy[asyncio]` + `asyncpg` | ORM async PostgreSQL |
| `redis[asyncio]` | Cache et sessions |
| `httpx` | Client HTTP async (PLaTon API) |
| `llama-index-core` | Pipeline RAG |
| `llama-index-embeddings-huggingface` | Modèles d'embedding locaux |
| `llama-index-vector-stores-postgres` | Stockage pgvector |
| `llama-index-retrievers-bm25` | Recherche lexicale BM25 |
| `sentence-transformers` | Reranking croisé |
| `google-genai` | Provider Gemini |
| `PyJWT` | Décodage JWT PLaTon |
| `pypdf` + `python-docx` | Extraction texte fichiers |

### Frontend

| Librairie | Rôle |
|---|---|
| `@angular/core` v19 | Framework SPA avec Signals |
| `@angular/ssr` | Server-Side Rendering |
| `typescript` | Typage statique |
| `rxjs` | Reactive extensions (utilisé partiellement) |
| `sass` | Styles SCSS |
| `monaco-editor` | Éditeur code intégré |

