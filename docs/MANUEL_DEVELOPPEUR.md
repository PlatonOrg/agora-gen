# Manuel Développeur — Agora AI Agent

## 1. Prérequis

### 1.1 Logiciels nécessaires

| Logiciel | Version minimum | Usage |
|----------|----------------|-------|
| Docker | 24+ | Conteneurisation |
| Docker Compose | v2 | Orchestration services |
| Node.js | 20+ | Développement frontend (optionnel, pour IDE) |
| Python | 3.11+ | Développement backend (optionnel, pour IDE) |
| Git | 2.40+ | Versioning |

### 1.2 Comptes et accès

- Compte PLaTon (pour l'authentification OAuth)
- Clé API du fournisseur LLM configuré (voir `resources/llm_providers.json`)

---

## 2. Installation

### 2.1 Cloner le dépôt

```bash
git clone <url-du-repo> agora-gen
cd agora-gen
```

### 2.2 Configuration des variables d'environnement

Créer un fichier `.env.dev` à la racine (voir `SECRETS.md` pour la liste complète) :

```env
# PostgreSQL
POSTGRES_USER=agora
POSTGRES_PASSWORD=<mot-de-passe>
POSTGRES_DB=agora_db
DATABASE_URL=postgresql+asyncpg://agora:<mot-de-passe>@db:5432/agora_db

# Redis
REDIS_URL=redis://redis:6379

# PLaTon OAuth
PLATON_BASE_URL=https://platon.univ-eiffel.fr
PLATON_CLIENT_ID=<client-id>
PLATON_CLIENT_SECRET=<client-secret>
SESSION_SECRET=<secret-aléatoire>
FRONTEND_URL=http://localhost

# LLM
LLM_PROVIDERS_PATH=/app/resources/llm_providers.json

# Embedding
EMBED_MODEL_HF_REPO_ID=intfloat/multilingual-e5-large-instruct
EMBED_MODEL_PATH=/opt/models/intfloat_multilingual-e5-large-instruct
```

### 2.3 Configuration des fournisseurs LLM

Éditer `resources/llm_providers.json` :

```json
[
  {
    "name": "cerebras",
    "kind": "openai_compatible",
    "base_url": "https://api.cerebras.ai/v1",
    "api_key": "<votre-clé>",
    "default_model": "gpt-oss-120b",
    "default": true
  }
]
```

Types supportés : `openai_compatible`, `ragustave`, `gemini`, `ollama`, `openrouter`, `cerebras`.

### 2.4 Lancement

```bash
# Développement (avec hot-reload)
docker compose --env-file .env.dev up --build -d

# Production
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 2.5 Initialisation de la base de données

Lors du premier lancement :

```bash
# Charger le contenu statique (composants, metadata)
docker compose exec api python scripts/db/db_static_content.py

# Indexer les exercices pour le RAG vectoriel
docker compose exec api python scripts/db/db_populate_vectors.py

# Créer les tables de logs
docker compose exec api python scripts/db/db_setup_log_tables.py
```

---

## 3. Architecture du code

### 3.1 Backend (Python / FastAPI)

Voir `docs/ARCHITECTURE.md` pour le détail complet.

Points clés pour les développeurs :

- **Endpoints** : `back/src/api/v1/endpoints/` — Chaque fichier est un routeur FastAPI
- **Services** : `back/src/services/` — Logique métier, pas de dépendance HTTP
- **Infra** : `back/src/infra/` — Accès aux systèmes externes (DB, Redis, LLM, PLaTon)
- **Workflows** : `back/src/workflows/` — Orchestration de la génération

Conventions :
- Toutes les fonctions de service sont `async`
- Les dépendances sont injectées via FastAPI `Depends()`
- Les modèles Pydantic sont dans `services/models/` et `infra/log/models.py`
- Les settings runtime sont gérés par `runtime_config_service.py` (enum `SettingKey`)

### 3.2 Frontend (Angular 19)

Points clés :

- **Standalone components** : Pas de modules Angular, chaque composant déclare ses imports
- **Signals** : État réactif via `signal()`, `computed()`, `effect()`
- **Services** : Injection via `inject()` (pas de constructeur injection)
- **SSE** : `ChatService` gère le flux SSE avec `EventSource` et parsing JSON

Conventions :
- Les fichiers SCSS utilisent des variables CSS (`--brand-*`)
- Les composants sont dans `features/<domaine>/components/`
- Les modèles TypeScript sont dans `features/<domaine>/models/`

---

## 4. Scripts utilitaires

### 4.1 Base de données

| Script | Commande | Description |
|--------|----------|-------------|
| `db_static_content.py` | `docker compose exec api python scripts/db/db_static_content.py` | Charge les composants et métadonnées |
| `db_populate_vectors.py` | `docker compose exec api python scripts/db/db_populate_vectors.py` | Indexe les exercices pour le RAG |
| `db_setup_log_tables.py` | `docker compose exec api python scripts/db/db_setup_log_tables.py` | Crée/recrée les tables de logs (destructif) |
| `db_restore.py` | `python back/scripts/db/db_restore.py <dump.dump>` | Restaure un dump PostgreSQL |

### 4.2 Benchmarks

| Script | Commande | Description |
|--------|----------|-------------|
| `run_benchmark.py` | `docker compose exec api python scripts/benchmarks/run_benchmark.py` | Benchmark du modèle d'embedding |
| `run_tests.py` | `docker compose exec api python scripts/benchmarks/run_tests.py` | Tests de performance |

### 4.3 Tests

```bash
# Tous les tests
docker compose exec api pytest -v

# Tests d'un package spécifique
docker compose exec api pytest -v tests/services/

# Tests avec couverture
docker compose exec api pytest --cov=src -v
```

---

## 5. Environnement de développement

### 5.1 IDE recommandé

- **JetBrains IntelliJ / WebStorm / PyCharm** ou **VS Code**
- Extensions recommandées : Angular Language Service, Python, Docker

### 5.2 Hot-reload

- **Frontend** : Le code source est monté dans le conteneur Docker. Les modifications dans `front/src/` sont détectées automatiquement par le serveur Angular dev
- **Backend** : Le code source est monté via volumes. Uvicorn recharge automatiquement à chaque modification dans `back/src/`

### 5.3 Accès direct aux services

| Service | URL |
|---------|-----|
| Frontend | http://localhost |
| Backend API | http://localhost:8000 |
| Swagger API | http://localhost:8000/docs |
| Base de données | `docker compose exec db psql -U agora -d agora_db` |

### 5.4 Logs

Les fichiers de logs sont écrits dans `resources/logs/` :
- `app.log` : Log principal de l'application
- `file_uploads.log` : Logs des uploads de fichiers
- `rag.log` : Logs du système RAG

---

## 6. Déploiement en production

### 6.1 Build des images

```bash
# Build frontend
docker build -t agora-frontend:latest -f front/Dockerfile .

# Build backend
docker build -t agora-backend:latest -f back/Dockerfile .
```

### 6.2 Configuration production

- Utiliser `docker-compose.prod.yml`
- Créer un fichier `.env.prod` avec les variables de production
- Pas d'Ollama en production — configurer un fournisseur LLM distant
- Configurer HTTPS via un reverse proxy (Traefik, Caddy, etc.)

### 6.3 Maintenance

```bash
# Backup de la base de données
docker compose exec db pg_dump -U agora -d agora_db > backup_$(date +%Y%m%d).sql

# Restauration
docker compose exec db psql -U agora -d agora_db < backup.sql

# Mise à jour des images
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## 7. Contribution

### 7.1 Conventions de code

- **Python** : PEP 8, type hints obligatoires, docstrings pour les fonctions publiques
- **TypeScript** : ESLint strict, interfaces pour les modèles de données
- **Commits** : Messages descriptifs en anglais, préfixés (feat:, fix:, refactor:, docs:)

### 7.2 Workflow de développement

1. Créer une branche depuis `main`
2. Développer et tester localement
3. Exécuter les tests (`pytest -v`)
4. Créer une merge/pull request
5. Revue de code avant merge

