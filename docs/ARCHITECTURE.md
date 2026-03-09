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

### 2.4 Séquence de démarrage du backend

Le backend suit une séquence de démarrage en deux phases :

**Phase critique (bloquante — doit compléter avant que `/health` réponde) :**
1. Connexion PostgreSQL + Redis
2. Création/vérification des tables de logs
3. Setup DB (tables ressources, sync tracker)
4. Chargement de la configuration runtime depuis la base

**Phase de fond (non-bloquante — démarre en parallèle) :**
1. Téléchargement du modèle d'embedding HuggingFace (si absent)
2. Sync des docs PLaTon depuis GitHub (détection de changements par SHA)
3. Reconstruction de `metadata.json` (si docs changées)
4. Initialisation des services RAG (embedding + pgvector)
5. Synchronisation des ressources PLaTon → base locale
6. Population / mise à jour des vecteurs d'exercices
7. Boucle de sync quotidienne (toutes les 24h)

---

## 3. Backend

### 3.1 Flux de génération d'exercice

1. **Réception** : `POST /api/v1/chat/` reçoit un `ChatRequest` (SSE streaming)
2. **Détection première requête vs modification** : `_exercise_is_empty()` analyse l'état de l'exercice (titre, énoncé, composants, etc.) pour décider si c'est une première génération ou une modification. Cette logique est purement déterministe (pas de signal en mémoire).
3. **Si modification (exercice non vide)** : Le workflow saute la recherche RAG et la sélection de composants. Le mode est verrouillé sur `"template"` ou `"pure"` selon l'état de l'exercice (`config_variables` présentes → template). ⚠️ *Voir ISSUES_ET_AMELIORATIONS.md — problème #8.*
4. **Si première génération** :
   - **Sélection de composants** : Le LLM sélectionne les composants PLaTon pertinents pour la requête
   - **Recherche RAG** : Récupération d'exercices et templates similaires via pgvector
   - **Décision template/pur** : Si le meilleur template RAG dépasse le seuil (`TEMPLATE_SCORE_THRESHOLD`), on utilise un template existant ; sinon, génération pure. Si `force_pure_exercise=true`, la sélection de template est ignorée
5. **Génération LLM** : Appel au LLM avec prompt système, documentation des composants, exemples d'exercices, et contexte utilisateur
6. **Sandbox** : Compilation et exécution sur PLaTon (builder + grader)
7. **Retry** : Si erreur sandbox, le retry handler tente des corrections automatiques (jusqu'à `SANDBOX_RETRY_MAX_ATTEMPTS`)
8. **Logging** : Chaque génération (succès ou échec) est enregistrée dans la table `exo_generation`

### 3.2 Modèle de données (PostgreSQL)

Tables principales :
- `log_conversation` : Conversations (regroupement de générations)
- `exo_generation` : Génération d'exercice (requête, statut)
- `exo_generation_result` : Résultat (sortie LLM, tokens, retry)
- `exo_generation_rag_search` : Recherche RAG associée
- `exo_generation_component_selection` : Sélection de composants
- `discussion_generation` : Génération de discussion (Q&A docs)
- `publish_event` : Publication d'exercice sur PLaTon
- `app_setting` : Paramètres runtime configurables

### 3.3 Paramètres runtime configurables

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

### 4.1 Technologies clés

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
- Images Docker buildées automatiquement par GitHub Actions et poussées vers GHCR (`ghcr.io/salemsd/agora-gen/backend` et `.../frontend`)
- Chaque image est taguée `:latest` ET avec le SHA du commit (rollback possible)
- `docker-compose.prod.yml` pour la production : pas d'Ollama, ressources limitées, healthchecks
- Le frontend est servi sur le port `8080` du conteneur — Nginx (hôte) proxifie vers ce port
- Les modèles d'embedding sont montés depuis `/opt/models` sur l'hôte
- Les docs PLaTon sont montées depuis `/opt/agora/resources/docs`

Pour le guide de déploiement complet (VPS, Nginx, HTTPS, CI/CD), voir [`MANUEL_DEVELOPPEUR.md`](MANUEL_DEVELOPPEUR.md#6-déploiement-en-production).

### Développement
- `docker-compose.yml` avec hot-reload et volumes montés
- Base de données exposée sur le port `5433` de l'hôte


