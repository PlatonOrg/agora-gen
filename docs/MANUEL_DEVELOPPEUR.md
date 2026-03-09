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

- Compte PLaTon avec droits admin (pour la synchronisation automatique des ressources)
- Clé API du fournisseur LLM configuré (voir `resources/llm_providers.json`)

---

## 2. Installation

### 2.1 Cloner le dépôt

```bash
git clone <url-du-repo> agora-gen
cd agora-gen
```

### 2.2 Configuration des variables d'environnement

Partir du fichier d'exemple fourni et le compléter :

```bash
cp .env.example .env.dev
# Remplir toutes les valeurs (PLaTon OAuth, mots de passe, clé LLM, etc.)
```

Toutes les variables sont décrites et commentées dans `.env.example`. Voir aussi `SECRETS.md` pour les variables sensibles utilisées en CI/CD.

### 2.3 Configuration des fournisseurs LLM

Éditer `resources/llm_providers.json`. Les clés API ne sont **jamais** écrites directement dans ce fichier (il est commité) — elles sont référencées via des placeholders `${VAR_NAME}` résolus depuis les variables d'environnement au démarrage.

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

Les variables correspondantes (`CEREBRAS_API_KEY`, `GROQ_API_KEY`, `RAGUSTAVE_API_KEY`, `OPENROUTER_API_KEY`…) sont à définir dans `.env.dev` ou `.env.prod`.

Types supportés : `openai_compatible`, `ragustave`, `gemini`, `openrouter`, `cerebras`.

### 2.4 Lancement

```bash
# Développement (avec hot-reload)
docker compose --env-file .env.dev up --build -d

# Production
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 2.5 Initialisation de la base de données

Toute l'initialisation est **automatique** au démarrage du backend. Le service `run_startup_setup` (dans `infra/db/setup_service.py`) exécute à chaque démarrage, de manière idempotente :

1. Création des tables manquantes (via SQLAlchemy `create_all`)
2. Ajout des colonnes nouvelles déclarées dans les modèles
3. Application des migrations versionnées (`schema_migration_version`)
4. Synchronisation des prompts système (fichiers `.txt` → table `log_prompt`)

En arrière-plan (non-bloquant), le backend effectue également :
- Téléchargement du modèle d'embedding et des docs PLaTon (si absents ou mis à jour)
- Synchronisation des ressources PLaTon → base locale
- Population / mise à jour des vecteurs RAG

**Aucune commande manuelle n'est nécessaire** pour un premier lancement ou une mise à jour.

---

## 3. Architecture du code

### 3.1 Backend (Python / FastAPI)

Voir `docs/ARCHITECTURE.md` pour le détail complet.

Points clés pour les développeurs :

- **Endpoints** : `back/src/api/v1/endpoints/` — Chaque fichier est un routeur FastAPI
- **Services** : `back/src/services/` — Logique métier, pas de dépendance HTTP directe
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

### 4.1 Benchmarks

| Script | Commande | Description |
|--------|----------|-------------|
| `run_benchmark.py` | `docker compose exec api python scripts/benchmarks/run_benchmark.py` | Benchmark du modèle d'embedding |
| `run_tests.py` | `docker compose exec api python scripts/benchmarks/run_tests.py` | Tests de performance |

### 4.2 Tests

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

Cette section décrit le processus complet pour déployer Agora sur un VPS (testé sur OVH/Ubuntu 22.04). Le pipeline CI/CD GitHub Actions automatise les étapes 6.4 et suivantes à chaque push sur `main`.

### 6.1 Préparer le VPS

Se connecter au VPS en SSH (en tant que `root` ou utilisateur sudo), puis :

```bash
# 1. Mettre à jour le système
apt-get update && apt-get upgrade -y

# 2. Installer les dépendances système
apt-get install -y ca-certificates curl gnupg ufw nginx certbot python3-certbot-nginx git

# 3. Ajouter le dépôt Docker officiel
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Installer Docker
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Vérifier l'installation :

```bash
docker --version
docker compose version
```

### 6.2 Configurer le pare-feu (UFW)

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status
```

### 6.3 Préparer le répertoire de l'application

```bash
# Créer le répertoire de déploiement
mkdir -p /opt/agora

# Créer le répertoire pour les modèles d'embedding (monté dans le conteneur)
mkdir -p /opt/models

# Le pipeline CI/CD écrira docker-compose.prod.yml et .env.prod dans /opt/agora
```

### 6.4 Configurer Nginx comme reverse proxy

Le frontend écoute sur le port `8080` à l'intérieur de Docker. Nginx expose le port `80` (puis `443` après HTTPS) et proxifie vers Docker. Les SSE (Server-Sent Events) nécessitent une configuration spéciale de buffering.

Créer le fichier `/etc/nginx/sites-available/agora` :

```nginx
server {
    listen 80;
    server_name <votre-domaine-ou-ip.nip.io>;

    location / {
        proxy_pass http://localhost:8080;

        # HTTP/1.1 keep-alive vers l'upstream
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # SSE / Streaming : désactiver tout buffering
        proxy_buffering off;
        proxy_cache off;
        gzip off;
        proxy_set_header X-Accel-Buffering no;

        # Longs timeouts pour les flux de génération (peut durer plusieurs minutes)
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;

        # En-têtes proxy standards
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Activer le site et recharger Nginx :

```bash
ln -s /etc/nginx/sites-available/agora /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

### 6.5 Configurer HTTPS avec Let's Encrypt

```bash
certbot --nginx -d <votre-domaine> --non-interactive --agree-tos -m <votre-email>
```

Certbot modifiera automatiquement la configuration Nginx pour rediriger HTTP → HTTPS et insérer les certificats. Les certificats sont renouvelés automatiquement via un timer systemd.

> **Astuce nip.io :** Si vous n'avez pas encore de domaine et souhaitez un certificat valide rapidement, vous pouvez utiliser un sous-domaine nip.io : `<IP>.nip.io` (ex. `51.83.162.50.nip.io`). Let's Encrypt émettra un certificat pour ce nom.

### 6.6 Configurer le PLaTon OAuth Callback URL

Dans la configuration OAuth de PLaTon, l'URL de callback doit pointer vers votre domaine de production :

```
https://<votre-domaine>/auth/callback
```

Dans le `.env.prod` (et le secret `ENV_PROD` GitHub), assurez-vous que :

```env
PLATON_CALLBACK_URL=https://<votre-domaine>/auth/callback
SESSION_COOKIE_SECURE=true
AGORA_ENV=production
```

### 6.7 Configurer les secrets GitHub Actions

Le pipeline CI/CD nécessite les secrets suivants configurés dans GitHub (voir `SECRETS.md` pour le détail complet) :

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | IP ou domaine du VPS |
| `VPS_USER` | Utilisateur SSH (ex. `root`) |
| `VPS_SSH_KEY` | Clé privée SSH (contenu complet) |
| `GH_PAT` | Personal Access Token GitHub (scope `read:packages`) |
| `ENV_PROD` | Contenu complet du fichier `.env.prod` |

Pour générer et copier une clé SSH vers le VPS :

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy"
ssh-copy-id -i ~/.ssh/id_ed25519.pub <USER>@<VPS_HOST>
```

La clé privée (`cat ~/.ssh/id_ed25519`) est à coller dans le secret `VPS_SSH_KEY`.

### 6.8 Contenu du `.env.prod` (secret `ENV_PROD`)

Partir du fichier d'exemple fourni dans le dépôt et le compléter avec les valeurs de production :

```bash
cp .env.prod.example .env.prod
# Remplir toutes les valeurs, notamment :
# - POSTGRES_PASSWORD, REDIS_PASSWORD, SESSION_SECRET
# - PLATON_CLIENT_ID, PLATON_CLIENT_SECRET
# - PLATON_ADMIN_USERNAME, PLATON_ADMIN_PASSWORD
# - PLATON_CALLBACK_URL=https://<votre-domaine>/auth/callback
# - AGORA_ENV=production, SESSION_COOKIE_SECURE=true
```

Une fois complété, coller l'intégralité du contenu de ce fichier dans le secret GitHub `ENV_PROD`.

### 6.9 Pipeline CI/CD — Fonctionnement

À chaque push sur la branche `main`, le fichier `.github/workflows/deploy.yml` exécute :

**Job `build-and-push`** :
1. Checkout du code source
2. Build de l'image Docker backend (`back/Dockerfile`) et push vers `ghcr.io/salemsd/agora-gen/backend`
3. Build de l'image Docker frontend (`front/Dockerfile`) et push vers `ghcr.io/salemsd/agora-gen/frontend`
4. Les images sont taguées `:latest` ET avec le SHA du commit (immuable, pour rollback)

**Job `deploy`** (nécessite `build-and-push` + environnement `production`) :
1. Copie de `docker-compose.prod.yml` vers `/opt/agora` sur le VPS via SCP
2. Connexion SSH au VPS :
   - Écriture de `.env.prod` depuis le secret (avec nettoyage des retours chariot Windows)
   - Validation des variables requises (`POSTGRES_USER`, `POSTGRES_PASSWORD`, etc.)
   - Authentification à GHCR avec le `GH_PAT`
   - Pull des images exactes (par digest SHA, pas `:latest`) pour garantir la cohérence
   - Re-tag des images en `:latest`
   - `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --remove-orphans`

> **Protection d'environnement :** Le job `deploy` est associé à l'environnement GitHub `production`. Vous pouvez y configurer des règles de protection (validateurs requis, délai d'attente) dans *Settings > Environments > production*.

### 6.10 Premier déploiement

Après le premier déploiement automatique, aucune étape manuelle n'est nécessaire. Le backend initialise automatiquement la base de données (tables, migrations, prompts) au démarrage, puis synchronise les ressources PLaTon et les vecteurs RAG en arrière-plan.

Il suffit d'attendre que le healthcheck du conteneur `api` passe à `healthy` (visible avec `docker compose -f /opt/agora/docker-compose.prod.yml ps`) avant d'accéder à l'application.

### 6.11 Maintenance en production

```bash
# Voir les logs des containers
docker compose -f /opt/agora/docker-compose.prod.yml logs -f api
docker compose -f /opt/agora/docker-compose.prod.yml logs -f frontend

# Backup de la base de données
docker compose -f /opt/agora/docker-compose.prod.yml exec db \
  pg_dump -U agora -d agora_db > /opt/agora/backup_$(date +%Y%m%d_%H%M).sql

# Restauration d'un backup
docker compose -f /opt/agora/docker-compose.prod.yml exec -T db \
  psql -U agora -d agora_db < /opt/agora/backup_<date>.sql

# Forcer un redéploiement manuel (sans push Git)
cd /opt/agora
echo "$GH_PAT" | docker login ghcr.io -u salemsd --password-stdin
docker compose -f docker-compose.prod.yml --env-file .env.prod pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --remove-orphans

# Vérifier l'état des containers
docker compose -f /opt/agora/docker-compose.prod.yml ps

# Renouveler manuellement le certificat SSL
certbot renew --dry-run   # test
certbot renew             # renouvellement réel
```

### 6.12 Ajouter un nouveau composant PLaTon

Lorsqu'un nouveau composant web est ajouté dans PLaTon (par l'équipe PLaTon), pour qu'il soit reconnu et utilisable par Agora :

1. **Vérifier la documentation MDX** : La page `.mdx` du composant dans le dépôt `PlatonOrg/platon` (sous `apps/docs/`) doit respecter ce format :
   ```mdx
   ---
   title: Nom du composant
   description: Description courte.
   ---

   # `wc-nom-du-composant`

   ## Documentation

   Description détaillée…

   ## API

   <ComponentProperties schema={{
     "type": "object",
     "properties": {
       "ma-propriete": { "type": "string", "description": "…" }
     }
   }} />
   ```

2. **Au redémarrage du backend**, Agora télécharge automatiquement les nouvelles docs MDX depuis GitHub (via `platon_docs_downloader.py`) et reconstruit `resources/docs/components/metadata.json` si des changements sont détectés.

3. **Fichier de prompt optionnel** : Si le composant nécessite des instructions de génération spécifiques pour le LLM, créer un fichier `resources/prompts/system_prompts/wc_nom_du_composant.txt` en suivant le format des fichiers existants (ex. `wc_match_list.txt`, `drag_drop.txt`).

4. **Composants bannis** : Si un composant ne doit jamais être proposé, l'ajouter à la liste `BANNED_COMPONENTS` dans `back/src/core/config_app.py`.

---

## 7. Contribution

### 7.1 Conventions de code

- **Python** : PEP 8, type hints obligatoires, docstrings pour les fonctions publiques
- **TypeScript** : ESLint strict, interfaces pour les modèles de données
- **Commits** : Messages descriptifs en anglais, préfixés (`feat:`, `fix:`, `refactor:`, `docs:`)

### 7.2 Workflow de développement

1. Créer une branche depuis `main`
2. Développer et tester localement
3. Exécuter les tests (`docker compose exec api pytest -v`)
4. Créer une merge/pull request
5. Revue de code avant merge
6. Le merge sur `main` déclenche automatiquement le déploiement en production
