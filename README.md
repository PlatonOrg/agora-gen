# Agora AI Agent — Générateur d'exercices PLaTon

Agora est une application fullstack permettant aux enseignants de générer des exercices [PLaTon](https://platon.univ-eiffel.fr) à l'aide d'un agent IA conversationnel. Elle combine un frontend Angular 19, un backend FastAPI, une base de données PostgreSQL+pgvector pour le RAG vectoriel, et Redis pour les sessions.

---

## Table des matières

- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Lancement rapide (développement)](#lancement-rapide-développement)
- [Configuration](#configuration)
  - [Variables d'environnement](#variables-denvironnement)
  - [Fournisseurs LLM](#fournisseurs-llm)
- [Commandes Docker utiles](#commandes-docker-utiles)
- [Scripts utilitaires](#scripts-utilitaires)
- [Tests](#tests)
- [Déploiement en production](#déploiement-en-production)
- [URLs et ports](#urls-et-ports)
- [Documentation complète](#documentation-complète)

---

## Architecture

| Service | Technologie | Rôle |
|---------|-------------|------|
| `frontend` | Angular 19 + Nginx | Interface utilisateur, proxy API |
| `api` | FastAPI + Uvicorn (Python 3.11) | API REST + SSE streaming |
| `db` | PostgreSQL 16 + pgvector | Données métier + embeddings RAG |
| `redis` | Redis 7 | Sessions, cache, signal d'arrêt |

Pour l'architecture détaillée, voir [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/) v2

---

## Lancement rapide (développement)

```bash
# 1. Cloner le dépôt
git clone <url-du-repo> agora-gen
cd agora-gen

# 2. Créer le fichier d'environnement
cp .env.example .env.dev
# Éditer .env.dev et renseigner les valeurs (voir SECRETS.md)

# 3. Lancer tous les services avec hot-reload
docker compose --env-file .env.dev up --build -d
```

L'application est ensuite accessible sur **http://localhost**.

> **Base de données :** Toute l'initialisation (tables, migrations, prompts, synchronisation des ressources PLaTon, population des vecteurs RAG) est effectuée **automatiquement** par le backend au démarrage. Aucune commande manuelle n'est nécessaire.

---

## Configuration

### Variables d'environnement

Copier le fichier d'exemple correspondant à votre environnement et le remplir :

```bash
# Développement
cp .env.example .env.dev

# Production
cp .env.prod.example .env.prod
```

Toutes les variables sont décrites et commentées dans ces fichiers. Les secrets sensibles (clés API, tokens) sont documentés dans [`SECRETS.md`](SECRETS.md).

### Fournisseurs LLM

Les fournisseurs LLM sont déclarés dans `resources/llm_providers.json`. Une entrée doit avoir `"default": true`.

Les clés API ne sont **jamais** écrites directement dans ce fichier (il est commité). Elles sont référencées via des placeholders `${VAR_NAME}` qui sont résolus depuis les variables d'environnement au démarrage.

```json
[
  {
    "name": "cerebras",
    "kind": "cerebras",
    "api_key": "${CEREBRAS_API_KEY}",
    "default_model": "gpt-oss-120b",
    "default": true
  },
  {
    "name": "groq",
    "kind": "openai_compatible",
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": "${GROQ_API_KEY}",
    "default_model": "llama-3.3-70b-versatile"
  }
]
```

Les variables correspondantes (`CEREBRAS_API_KEY`, `GROQ_API_KEY`, `RAGUSTAVE_API_KEY`, `OPENROUTER_API_KEY`, etc.) sont à définir dans `.env.dev` ou `.env.prod` — voir les fichiers d'exemple.

Kinds supportés : `openai_compatible`, `ragustave`, `gemini`, `openrouter`, `cerebras`.

> Le fournisseur et le modèle actifs peuvent être changés à chaud depuis le panneau d'administration, sans redémarrage.

---

## Commandes Docker utiles

```bash
# Démarrer tous les services (build inclus)
docker compose --env-file .env.dev up --build -d

# Arrêter tous les services
docker compose down

# Voir les logs d'un service
docker compose logs -f api
docker compose logs -f frontend

# Accéder à la base de données
docker compose exec db psql -U agora -d agora_db

# Créer un dump de la base de données
docker compose exec db pg_dump -U agora -d agora_db -f dump.sql

# Réinitialiser complètement la base (destructif)
docker compose exec db psql -U agora -d agora_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

---

## Scripts utilitaires

### Restauration de base de données

```bash
# Depuis un fichier .sql dans le conteneur
docker compose exec db psql -U agora -d agora_db -f dump.sql
```

---

## Tests

```bash
# Lancer tous les tests
docker compose exec api pytest -v

# Lancer un package de tests spécifique
docker compose exec api pytest -v tests/services/

# Lancer les tests avec couverture de code
docker compose exec api pytest --cov=src -v
```

---

## Déploiement en production

Le déploiement en production est géré via le pipeline CI/CD GitHub Actions (`.github/workflows/deploy.yml`). Tout push sur la branche `main` déclenche :

1. Les tests unitaires
2. Le build et le push des images Docker vers GitHub Container Registry (GHCR)
3. Le déploiement automatique sur le VPS via SSH

Pour la configuration complète du VPS et du pipeline CI/CD, voir [`docs/MANUEL_DEVELOPPEUR.md`](docs/MANUEL_DEVELOPPEUR.md#6-déploiement-en-production).

Pour la gestion des secrets GitHub Actions, voir [`SECRETS.md`](SECRETS.md).

---

## URLs et ports

| Service | URL (développement) |
|---------|---------------------|
| Application (frontend) | http://localhost |
| API backend | http://localhost:8000 |
| Documentation Swagger | http://localhost:8000/docs |
| Base de données | `docker compose exec db psql -U agora -d agora_db` |

---

## Documentation complète

| Document | Description |
|----------|-------------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Architecture technique détaillée |
| [`docs/MANUEL_DEVELOPPEUR.md`](docs/MANUEL_DEVELOPPEUR.md) | Guide développeur, setup, déploiement production |
| [`docs/ISSUES_ET_AMELIORATIONS.md`](docs/ISSUES_ET_AMELIORATIONS.md) | Problèmes connus et pistes d'amélioration |
| [`SECRETS.md`](SECRETS.md) | Configuration des secrets GitHub Actions |

