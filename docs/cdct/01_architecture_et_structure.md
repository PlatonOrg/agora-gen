# Cahier des Charges Technique — Agora AI Agent
## Partie I : Architecture et Structure du Projet

---

## Préambule

Ce document décrit l'architecture technique d'Agora, la structure de ses composants logiciels, et la finalité de chacun. L'objectif est de donner à un développeur rejoignant le projet une vision claire et globale du système — comment il est découpé, quelles technologies le composent, et comment les grands blocs communiquent entre eux.

---

## 1. Vue d'ensemble architecturale

Agora est une application web full-stack déployée sous Docker. Elle se compose de quatre services indépendants qui communiquent sur un réseau Docker interne (`agora_net`).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Réseau Docker : agora_net                          │
│                                                                             │
│  ┌──────────────────┐    HTTP/SSE     ┌──────────────────────────────────┐  │
│  │                  │◀──────────────▶│                                  │  │
│  │  Frontend        │                │  Backend API                     │  │
│  │  Angular 20      │                │  FastAPI / Python                │  │
│  │  Port 80         │                │  Port 8000                       │  │
│  │  (Nginx)         │                │                                  │  │
│  └──────────────────┘                └─────────────┬────────────────────┘  │
│                                                    │                        │
│                                          ┌─────────┴──────────┐            │
│                                          │                    │            │
│                               ┌──────────▼──────┐  ┌─────────▼──────────┐ │
│                               │  PostgreSQL 16   │  │  Redis 7           │ │
│                               │  + pgvector      │  │  (cache + sessions)│ │
│                               │  Port 5432       │  │  Port 6379         │ │
│                               └─────────────────┘  └────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

           Services externes (hors réseau Docker)
           ┌──────────────────────────────────────┐
           │  PLaTon API    — plateforme pédagogique│
           │  Providers LLM — Cerebras / Gemini /  │
           │                  OpenRouter / Ollama  │
           │  GitHub API    — documentation PLaTon │
           │  HuggingFace   — modèle d'embedding   │
           └──────────────────────────────────────┘
```

### Responsabilités de chaque service

**Frontend (Angular 20 + Nginx)** : interface utilisateur complète. En développement, Angular CLI sert l'application avec hot-reload. En production, le bundle est compilé statiquement et servi par Nginx, qui fait également office de reverse proxy vers l'API backend — les appels `/api/v1/*` sont transmis au service backend sans que le frontend ait à connaître son adresse réseau interne.

**Backend API (FastAPI / Python)** : moteur principal de l'application. Il expose l'intégralité de la logique métier via une API REST et un flux SSE. Il est le seul service à interagir avec les LLM, PLaTon, et les tables de données.

**PostgreSQL 16 + pgvector** : base de données principale. Elle stocke les données métier (exercices, templates, composants), les logs de génération, la configuration à chaud, et la table vectorielle pgvector contenant les embeddings de toutes les ressources PLaTon.

**Redis 7** : cache distribué et store de sessions. Il stocke le contenu extrait des fichiers uploadés par les utilisateurs, les résultats d'appels PLaTon mis en cache pour les synchronisations, et les sessions courantes.

---

## 2. Structure du backend

### 2.1 Technologies utilisées

| Technologie | Rôle |
|---|---|
| **FastAPI** | Framework HTTP async. Gestion des routes, middlewares, validation des données d'entrée |
| **Uvicorn** | Serveur ASGI qui exécute FastAPI |
| **SQLAlchemy async** | ORM et couche d'accès aux données, avec asyncpg pour les appels non-bloquants |
| **Redis (redis-py)** | Client async pour le cache de fichiers et le cache des appels PLaTon |
| **LlamaIndex** | Framework RAG. Indexation vectorielle, connexion à pgvector, retrievers |
| **HuggingFace Embeddings** | Génération des vecteurs via le modèle E5 local (via `sentence-transformers`) |
| **PyTorch** | Exécution du modèle d'embedding (CPU ou GPU selon disponibilité) |
| **httpx** | Client HTTP async pour tous les appels vers PLaTon, GitHub, et les LLM |
| **Pydantic v2** | Validation et sérialisation des modèles de données |
| **PyJWT** | Validation et décodage des tokens JWT émis par PLaTon |
| **cerebras-cloud-sdk** | SDK officiel Cerebras pour les appels LLM |
| **pypdf / python-docx / openpyxl** | Extraction de texte depuis les fichiers uploadés |

### 2.2 Organisation du code backend

Le code backend est découpé en quatre grandes couches, chacune ayant une responsabilité bien délimitée et ne communicant qu'avec la couche adjacente.

```
┌─────────────────────────────────────────────────────┐
│                  API  (api/v1/)                     │
│  Contrôleurs REST + SSE, validation des entrées,    │
│  authentification, formatage des réponses           │
└───────────────────────────┬─────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────┐
│             Services métier  (services/)             │
│  Logique applicative pure : génération, RAG,        │
│  correction sandbox, workspace, authentification    │
└───────────────────────────┬─────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────┐
│             Orchestration  (workflows/)              │
│  Coordination des services dans des séquences       │
│  complexes : pipeline de génération, retry handler  │
└───────────────────────────┬─────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────┐
│             Infrastructure  (infra/)                 │
│  Implémentations concrètes : accès DB, appels LLM,  │
│  gestion des fichiers, vectorisation, cache         │
└─────────────────────────────────────────────────────┘
```

**La couche API** expose les endpoints de l'application, regroupés par domaine fonctionnel : génération d'exercices (SSE), authentification, gestion de l'exercice courant et publication, catalogue de composants, consultation des logs, administration et statistiques, upload de fichiers, et recherche documentaire. Elle ne contient aucune logique métier — elle délègue immédiatement aux services.

**La couche services** contient toute la logique applicative : assemblage des prompts de génération, correction automatique des erreurs sandbox, sélection des composants par LLM, transformation des données entre les formats internes et PLaTon, gestion de la configuration à chaud, validation des tokens d'authentification. Ces services sont indépendants des détails d'implémentation (ils ne savent pas quel provider LLM est actif, ni quelle table SQL est utilisée).

**La couche workflows** orchestre les services dans des séquences à plusieurs étapes. C'est ici que résident le pipeline principal de génération (RAG → sélection de composants → LLM → sandbox → log) et la boucle de retry générique qui gère les erreurs sandbox. Cette couche est nécessaire parce que certains scénarios nécessitent de coordonner plusieurs services avec une logique de branchement conditionnelle.

**La couche infrastructure** fournit les implémentations concrètes : les adaptateurs pour chaque provider LLM (Cerebras, Gemini, OpenRouter, Ollama), l'accès aux tables de base de données via l'ORM, la vectorisation des ressources, le service de fichiers avec extraction de texte et stockage Redis, et les services d'initialisation au démarrage. Cette couche est interchangeable sans affecter les couches supérieures.

---

## 3. Structure du frontend

### 3.1 Technologies utilisées

| Technologie | Rôle |
|---|---|
| **Angular 20** | Framework SPA. Architecture basée sur les signaux (`signal()`) pour la réactivité, sans NgRx |
| **Angular SSR** | Rendu côté serveur Node.js pour le premier affichage (Express 5) |
| **Angular Material + ng-zorro-antd** | Bibliothèques de composants UI |
| **ngx-monaco-editor** | Éditeur de code Monaco (même base que VS Code) pour les champs de code |
| **ngx-markdown + highlight.js** | Rendu et coloration syntaxique du Markdown dans l'interface |
| **ngx-charts (Swimlane)** | Graphiques pour les statistiques de la page d'administration |
| **RxJS** | Gestion des flux d'événements asynchrones (SSE, observables) |

### 3.2 Organisation du code frontend

Le frontend est découpé en **features** (pages) et en **core** (services transversaux), avec un dossier **shared** pour les composants réutilisables.

```
┌──────────────────────────────────────────────────────────────────┐
│                         FEATURES (pages)                         │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │   Workspace      │  │    Logs       │  │  Administration    │  │
│  │  Génération      │  │  Historique   │  │  Config, stats,   │  │
│  │  d'exercices     │  │  Statistiques │  │  modèles LLM      │  │
│  └─────────────────┘  └──────────────┘  └────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                     Auth (login / callback)              │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     CORE (services transversaux)                 │
│  Communication API, gestion du flux SSE, authentification,       │
│  accès aux logs                                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     SHARED (composants réutilisables)            │
│  Composants UI génériques, pipes de transformation              │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 La page Workspace

C'est la page centrale et la plus complexe de l'application. Elle est organisée en trois panneaux redimensionnables :

- **Panneau gauche** : alternance entre le chat de génération / discussion documentaire et le navigateur de templates PLaTon
- **Panneau central** : éditeur de l'exercice en cours (champs texte, éditeur de code Monaco pour builder et grader, aperçu des métadonnées)
- **Panneau droit** : sélecteur de composants PLaTon et aperçu de l'exercice dans un iframe PLaTon Player

L'état de cette page (exercice courant, historique de conversation, fichiers joints, dimensions des panneaux, flux SSE en cours) est géré par un ensemble de services Angular réactifs basés sur les signaux. Une façade unique expose toutes les actions et données aux composants, de sorte qu'aucun composant Angular ne gère d'état directement.

### 3.4 Gestion d'état

Le frontend n'utilise pas de store global centralisé (pas de NgRx). L'état est géré localement par page, via des **signaux Angular** (`signal()`, `computed()`). Ce choix convient à la taille du projet : une seule page active à la fois, sans partage d'état complexe entre routes.

### 3.5 Communication avec le backend

Tous les appels HTTP courants (GET, POST, PUT, DELETE) transitent par un service central qui encapsule l'API Fetch native. Pour la génération d'exercices, un service SSE dédié ouvre un flux `EventSource`, écoute les événements nommés émis par le backend, et met à jour les signaux réactifs du store au fil des événements reçus.

---

## 4. Le dossier `resources/`

Le dossier `resources/` est le **répertoire de travail partagé** entre le backend et, indirectement, le frontend. Il est monté comme volume Docker dans les conteneurs. Son contenu n'est pas embarqué dans l'image Docker — il persiste entre les redémarrages et peut être modifié sans rebuild.

```
resources/
├── llm_providers.json       ← Registre des providers LLM disponibles et leurs modèles
│
├── prompts/
│   └── system_prompts/      ← Fichiers .txt des prompts système versionnés
│       ├── pure_exercise.txt              (première génération libre)
│       ├── pure_exercise_modification.txt (modification d'exercice libre)
│       ├── template_exercise.txt          (première génération via template)
│       ├── template_exercise_modification.txt
│       ├── exercise_repair.txt            (correction d'erreur sandbox)
│       ├── component_selection.txt        (sélection des composants)
│       ├── platon_docs_qa.txt             (recherche documentaire)
│       └── [instructions spécifiques par composant complexe]
│
├── docs/
│   ├── platon_docs/         ← Documentation MDX de PLaTon (téléchargée depuis GitHub)
│   └── components/
│       └── metadata.json    ← Catalogue généré des composants PLaTon
│                               (tag, nom, catégorie, description, propriétés)
│
├── local_models/
│   └── intfloat_multilingual-e5-large-instruct/
│                            ← Modèle d'embedding local (~1.2 Go)
│                               Téléchargé automatiquement si absent
│
└── logs/
    ├── app.log              ← Journal applicatif principal
    ├── rag.log              ← Journal spécifique au pipeline RAG
    └── file_uploads.log     ← Journal des uploads de fichiers utilisateurs
```

### Le fichier `llm_providers.json`

Ce fichier est la source de vérité des fournisseurs LLM disponibles. Il déclare pour chaque provider son nom, son URL de base, et la liste de ses modèles. L'interface d'administration lit ce fichier pour proposer les choix disponibles, et le backend s'appuie dessus pour instancier les adaptateurs corrects. Modifier ce fichier et redémarrer suffit pour ajouter un nouveau fournisseur.

### Le dossier `prompts/system_prompts/`

Chaque fichier `.txt` correspond à un scénario d'appel LLM. Ils sont chargés depuis le disque sans cache mémoire : une modification en production prend effet immédiatement pour la prochaine génération. Au démarrage, ces fichiers sont synchronisés vers la base de données afin que chaque log de génération référence la version exacte du prompt utilisée.

Les instructions spécifiques aux composants complexes (`drag_drop.txt`, `wc_match_list.txt`, etc.) sont injectées dans le prompt de génération uniquement lorsque le composant concerné est sélectionné pour l'exercice. Ils contiennent des règles métier précises sur l'usage correct de ce composant dans un exercice PLaTon.

### Le modèle d'embedding

Le modèle `intfloat/multilingual-e5-large-instruct` est un modèle multilingue de 1024 dimensions, optimisé pour la recherche sémantique instructée. Il est hébergé localement pour deux raisons : performance (pas de latence réseau sur les embeddings) et confidentialité (les textes des exercices ne quittent pas l'infrastructure).

---

## 5. Schéma de la base de données

La base de données PostgreSQL est organisée en deux ensembles logiques : les **tables de ressources** (données PLaTon synchronisées) et les **tables de logs** (traces de toutes les générations).

```
TABLES DE RESSOURCES
──────────────────────────────────────────────────────────────────────
  component              template                exercise
  ─────────────          ────────────            ─────────────────────
  tag (unique)           platon_id (unique)       platon_id (unique)
  nom, catégorie         horodatages              lien vers template
  description                                     horodatages
  propriétés (JSON)
                          ↑                        ↑
                    template_component_link    exercise_component_link
                    (table de liaison)         (table de liaison)
                          ↓                        ↓
                                  component

  app_setting                         schema_migration_version
  ─────────────────────               ──────────────────────────
  clé / valeur / type                 version courante du schéma
  (paramètres admin)                  (migrations versionnées)

TABLES DE LOGS
──────────────────────────────────────────────────────────────────────
  log_conversation          ← regroupe plusieurs générations
  │
  └─▶ exo_generation        ← table centrale, une ligne = une génération
       ├── exo_generation_request      (la demande : texte, historique, fichiers)
       ├── exo_rag_search              (résultats RAG : scores, ressources)
       │     └── exo_rag_search_result (détail par résultat)
       ├── log_component_selection     (sélection de composants : raisonnement LLM)
       └── exo_generation_result       (sortie LLM, tokens, retry, statut, URL)

TABLE VECTORIELLE (pgvector)
──────────────────────────────────────────────────────────────────────
  agora_rag_embeddings_data   (gérée par LlamaIndex + pgvector)
  ─────────────────────────────────────────────
  texte source de l'embedding
  métadonnées  { platon_id, nom, type de ressource }
  vecteur dense 1024 dimensions
```

La table vectorielle est gérée par LlamaIndex. La recherche par similarité cosinus utilise l'opérateur pgvector `<=>`, indexé avec un index HNSW pour des performances en O(log n) sur l'ensemble du catalogue.

---

## 6. Flux d'authentification

L'authentification est entièrement déléguée à PLaTon. Agora ne gère pas de mots de passe ni d'identités — il fait confiance aux tokens JWT émis par PLaTon.

```
Utilisateur      Frontend Angular    PLaTon OAuth    Backend Agora
    │                  │                   │                │
    ├── Clic login ───▶│                   │                │
    │                  ├── Redirect ──────▶│                │
    │◀── Formulaire ───┤                   │                │
    ├── Identifiants ─▶│                   │                │
    │                  ├── POST /token ────▶│                │
    │                  │◀── JWT ───────────┤                │
    │                  │                                    │
    │                  ├── Toutes les requêtes              │
    │                  │   Authorization: Bearer JWT ──────▶│
    │                  │                         ┌──────────┴──────┐
    │                  │                         │ Validation JWT  │
    │                  │                         │ Extraction user │
    │                  │                         └──────────┬──────┘
    │                  │◀── Réponse ────────────────────────┤
```

Chaque requête authentifiée transmet le JWT dans l'en-tête `Authorization: Bearer`. Le backend valide la signature et extrait l'identité de l'utilisateur. Ce même token est transmis aux appels PLaTon effectués au nom de l'utilisateur (création de previews, publication) afin que les ressources créées lui soient attribuées sur la plateforme PLaTon.

---

*Document établi le 9 mars 2026 — source de vérité : code source de l'application.*
