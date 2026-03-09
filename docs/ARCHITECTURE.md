# Architecture Technique — Agora AI Agent

## 1. Vue d'ensemble

Agora est une application fullstack qui permet aux enseignants de générer des exercices PLaTon à l'aide d'un agent IA conversationnel. L'architecture combine :

- **Frontend** : Angular 19 (standalone components, SSR, signals)
- **Backend** : FastAPI (Python 3.11, async/await)
- **Base de données** : PostgreSQL 16 + pgvector (stockage RAG vectoriel)
- **Cache / Sessions** : Redis 7
- **LLM** : Multi-fournisseurs (OpenAI-compatible, Gemini, Ollama, Ragustave)
- **Conteneurisation** : Docker Compose (développement et production)

---

## 2. Infrastructure

### 2.1 Services Docker

| Service | Image | Port exposé | Rôle |
|---------|-------|-------------|------|
| `frontend` | Angular SSR + Nginx | 80 | Application web, proxy API |
| `backend` | FastAPI + Uvicorn | 8000 | API REST + SSE streaming |
| `db` | PostgreSQL 16 + pgvector | 5433 (dev) | Données métier + vecteurs RAG |
| `redis` | Redis 7 | 6379 | Sessions, cache fichiers, signal stop |
| `ollama` (dev only) | Ollama | 11434 | LLM local pour développement |

### 2.2 Réseau

Tous les services communiquent via le réseau Docker `agora_net`. Nginx (frontend) proxifie les requêtes `/api/` vers le backend. Le SSE streaming utilise des headers spéciaux (`X-Accel-Buffering: no`, `proxy_buffering off`).

### 2.3 Flux de données principal

```
Utilisateur → Nginx (Angular) → Backend FastAPI → LLM Provider
                                      ↕                ↕
                                PostgreSQL/pgvector   Redis
                                      ↕
                              PLaTon API (sandbox)
```

---

## 3. Backend

### 3.1 Structure des fichiers

```
back/src/
├── main.py                          # Point d'entrée, lifespan, middlewares CORS
├── api/v1/
│   ├── api.py                       # Agrégation des routers
│   ├── dependencies.py              # Injection (session DB, settings, session_id)
│   └── endpoints/
│       ├── auth.py                  # OAuth PLaTon (init, callback, user, logout)
│       ├── chat.py                  # SSE streaming, upload fichiers, stop, delete fichier
│       ├── context.py               # Cercles, topics, levels, templates, preview PLE
│       ├── exercises.py             # Tags, save/load exercice, publication PLaTon
│       ├── logs.py                  # Consultation logs de génération
│       ├── admin.py                 # Statistiques, config runtime, LLM options
│       └── platon_docs_qa.py        # Q&A documentation PLaTon (mode discussion)
├── core/
│   ├── config_app.py                # Settings centralisé (pydantic-settings, .env)
│   ├── di.py                        # Registre LLM (LLMProviderRegistry)
│   ├── logging_config.py            # Loggers rotatifs par fichier
│   ├── path_constants.py            # Chemins absolus (prompts, modèles)
│   └── sqlalchemy.py                # Engine asyncpg, session factory
├── infra/
│   ├── db/                          # Repositories (components, templates, settings)
│   ├── llm/                         # Providers LLM, wrapper, JSON facility
│   ├── files/                       # Parsing fichiers, résumés, stockage Redis
│   ├── log/                         # Persistance logs en DB (db_logger.py, models.py)
│   ├── platon/                      # Client HTTP PLaTon
│   └── vector/                      # Service d'indexation vectorielle
├── services/
│   ├── generation_service.py        # Génération LLM (pur + template)
│   ├── component_selection_service.py # Sélection de composants par LLM
│   ├── template_service.py          # Gestion des templates PLaTon
│   ├── sandbox_correction_service.py # Correction automatique sandbox
│   ├── runtime_config_service.py    # Configuration runtime en mémoire (SettingKey enum)
│   ├── logs_service.py              # Requêtes de consultation des logs
│   ├── admin_stats_service.py       # Agrégation statistiques admin
│   └── rag/                         # Service de retrieval vectoriel
└── workflows/
    ├── workflow.py                  # Orchestrateur principal (handle_chat)
    └── retry_handler.py             # Mécanisme de retry sandbox
```

### 3.2 Flux de génération d'exercice

1. **Réception** : `POST /api/v1/chat/` reçoit un `ChatRequest` (SSE streaming)
2. **Sélection de composants** : LLM sélectionne les composants PLaTon pertinents
3. **Recherche RAG** : Récupération d'exercices similaires via pgvector
4. **Décision template/pur** : Si le score RAG dépasse le seuil (`TEMPLATE_SCORE_THRESHOLD`), on utilise un template existant ; sinon, génération pure
5. **Génération LLM** : Appel au LLM avec prompt système, exemples, et contexte
6. **Sandbox** : Compilation et exécution sur PLaTon (builder + grader)
7. **Retry** : Si erreur sandbox, le retry handler tente des corrections automatiques (jusqu'à `SANDBOX_RETRY_MAX_ATTEMPTS`)
8. **Logging** : Chaque génération (succès ou échec) est enregistrée dans la table `exo_generation`

### 3.3 Modèle de données (PostgreSQL)

Tables principales :
- `log_conversation` : Conversations (regroupement de générations)
- `exo_generation` : Génération d'exercice (requête, statut)
- `exo_generation_result` : Résultat (sortie LLM, tokens, retry)
- `exo_generation_rag_search` : Recherche RAG associée
- `exo_generation_component_selection` : Sélection de composants
- `discussion_generation` : Génération de discussion (Q&A docs)
- `publish_event` : Publication d'exercice sur PLaTon
- `app_setting` : Paramètres runtime configurables

### 3.4 Paramètres runtime configurables

| Clé | Type | Défaut | Description |
|-----|------|--------|-------------|
| `TEMP_GENERATION` | float | 0.0 | Température de génération LLM |
| `NUM_EXAMPLE_EXERCISES` | int | 10 | Exercices exemples pour le RAG |
| `RAG_LOG_TOP_K` | int | 10 | Résultats RAG enregistrés |
| `PLATON_DOCS_TOP_K` | int | 8 | Chunks docs pour discussion |
| `SANDBOX_RETRY_MAX_ATTEMPTS` | int | 3 | Tentatives sandbox max |
| `SANDBOX_RETRY_TIMEOUT_SECONDS` | float | 120.0 | Timeout global retry |
| `FILE_UPLOAD_MAX_COUNT` | int | 5 | Fichiers joints max par session |
| `LOG_LEVEL` | str | INFO | Niveau de journalisation |
| `TEMPLATE_SCORE_THRESHOLD` | float | 0.85 | Score min pour sélection template |

---

## 4. Frontend

### 4.1 Structure des fichiers

```
front/src/app/
├── core/
│   ├── api/api.service.ts           # Service HTTP de base (fetch wrapper)
│   ├── auth/                        # Authentification OAuth
│   ├── llm/                         # Capabilities LLM, polling options
│   └── logging/logs.service.ts      # Service d'accès aux logs
├── features/
│   ├── workspace/                   # Espace de travail principal
│   │   ├── components/
│   │   │   ├── discussion/          # Panel de discussion (chat)
│   │   │   ├── exercise-content/    # Éditeur d'exercice
│   │   │   └── template-parameters/ # Paramètres template
│   │   └── services/
│   │       ├── chat.service.ts      # Communication SSE avec le backend
│   │       └── exercise.service.ts  # État de l'exercice en cours
│   ├── logging/                     # Pages de logs et détails
│   │   ├── components/
│   │   │   ├── log-conversations-view/    # Liste des conversations
│   │   │   ├── session-detail-view/       # Détail d'une conversation
│   │   │   ├── exo-generation-detail/     # Détail d'une génération
│   │   │   └── log-stats-view/            # Configuration runtime
│   │   └── models/log.model.ts            # Interfaces TypeScript
│   └── admin/                       # Tableau de bord administrateur
│       ├── components/admin-dashboard-page/ # Statistiques
│       └── services/admin-statistics.service.ts
└── shared/ui/                       # Composants réutilisables
```

### 4.2 Technologies clés

- **Angular 19** : Standalone components, signals, control flow (@if, @for)
- **Monaco Editor** : Édition de code PLaTon (builder, grader)
- **ngx-charts** : Graphiques pour le tableau de bord
- **SSE (Server-Sent Events)** : Streaming de la génération en temps réel

---

## 5. Sécurité

- Authentification OAuth via PLaTon (cookies de session)
- Sessions gérées dans Redis avec TTL configurable
- Pas de secrets exposés côté client
- Variables d'environnement via `.env` (voir `SECRETS.md`)

---

## 6. Déploiement

### Production
- Images Docker pré-buildées depuis GitHub Container Registry
- `docker-compose.prod.yml` pour la production
- Pas d'Ollama en production (fournisseur LLM distant requis)

### Développement
- `docker-compose.yml` avec hot-reload et volumes montés
- Ollama local pour les tests LLM

