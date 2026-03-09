# Cahier des Charges Technique — Agora AI Agent
## Partie III : Initialisation et Auto-Configuration du Système

---

## Préambule

Ce document décrit le mécanisme d'auto-initialisation d'Agora au démarrage. Il s'agit d'une des caractéristiques les plus remarquables du système : à partir d'un environnement vierge (base de données vide, aucun asset présent), Agora est capable de se configurer entièrement de manière autonome — sans intervention manuelle, sans scripts à exécuter, sans rechargement nécessaire.

Ce mécanisme est conçu pour être **idempotent** : l'exécuter une fois ou dix fois produit exactement le même état final. Il est également **résilient** : une étape qui échoue (GitHub inaccessible, PLaTon hors ligne) ne bloque pas les étapes indépendantes et ne fait pas planter le serveur.

---

## 1. Vue d'ensemble : le démarrage en deux chemins

Le démarrage d'Agora est organisé autour d'une distinction fondamentale entre ce qui est **critique** (le serveur ne doit pas répondre avant que ce soit prêt) et ce qui est **lourd** (cela peut se faire en arrière-plan pendant que le serveur est déjà opérationnel).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     DÉMARRAGE DU SERVEUR AGORA                              │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
               ┌───────────────▼────────────────┐
               │     CHEMIN CRITIQUE (bloquant)  │
               │  ─────────────────────────────  │
               │  1. Connexion PostgreSQL         │
               │  2. Connexion Redis              │
               │  3. Création des tables DB       │
               │  4. Migrations de schéma         │
               │  5. Chargement de la config      │
               └───────────────┬────────────────┘
                               │
                          ┌────▼─────┐
                          │  yield   │  ← Le serveur commence à répondre
                          │ /health  │    (healthchecks Docker satisfaits)
                          └────┬─────┘
                               │
               ┌───────────────▼────────────────────────────────────────────┐
               │     CHEMIN ARRIÈRE-PLAN (non-bloquant, asyncio task)       │
               │  ─────────────────────────────────────────────────────     │
               │  A. Setup des assets (modèle, docs PLaTon, metadata)       │
               │  B. Initialisation des services RAG                        │
               │  C. Synchronisation ressources PLaTon + vectorisation      │
               │  D. Lancement de la boucle de sync quotidienne             │
               └────────────────────────────────────────────────────────────┘
```

Cette architecture garantit que les sondes de santé Docker (`/health`) répondent immédiatement, évitant tout timeout de démarrage même sur des machines avec des ressources limitées.

---

## 2. Le chemin critique : infrastructure de base

### 2.1 Initialisation de la base de données et de Redis

Les connexions à PostgreSQL et Redis sont établies et testées. En cas d'échec (base indisponible, mauvais credentials), le serveur lève une exception critique et refuse de démarrer — ces deux composants sont des prérequis absolus.

La configuration Docker Compose exprime cette dépendance : le conteneur backend ne démarre que lorsque PostgreSQL et Redis ont passé leurs healthchecks respectifs (`pg_isready` pour PostgreSQL, `redis-cli ping` pour Redis).

### 2.2 Gestion du schéma de base de données

Immédiatement après la connexion, le système vérifie et maintient à jour le schéma de la base de données. Ce processus se décompose en trois niveaux complémentaires.

**Niveau 1 — Création des tables manquantes** : le système inspecte la liste des tables existantes en base (`pg_tables`) et compare avec le schéma déclaré dans les modèles ORM. Toute table absente est créée automatiquement (`CREATE TABLE IF NOT EXISTS`). Cela couvre le cas d'une installation fraîche : aucune table n'existe, toutes sont créées en un seul passage.

**Niveau 2 — Ajout de colonnes manquantes** : pour les tables déjà existantes, le système compare les colonnes en base (`information_schema.columns`) avec les colonnes déclarées dans les modèles. Toute colonne présente dans le modèle mais absente de la table est ajoutée avec `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Ce mécanisme permet de déployer une nouvelle version du code qui ajoute des champs sans migration manuelle.

**Niveau 3 — Migrations versionnées** : pour les changements de schéma plus complexes (modifications de types, ajout d'index, renommages, transformations de données), un système de migrations SQL versionnées est utilisé. La version courante du schéma est stockée dans une table dédiée (`schema_migration_version`). Au démarrage, toutes les migrations dont le numéro est supérieur à la version courante sont appliquées séquentiellement. Chaque migration s'exécute dans sa propre transaction : un échec ne laisse pas le schéma dans un état intermédiaire, et la version n'est incrémentée qu'après succès. Les migrations sont définies dans un fichier Python comme un dictionnaire `{version: sql_block}`.

```
Version en DB : 3
Migrations disponibles : 1, 2, 3, 4, 5
→ Applique migration 4 (commit), puis migration 5 (commit)
→ Version en DB = 5
```

### 2.3 Synchronisation des prompts

La dernière étape du chemin critique synchronise les fichiers de prompts système avec la base de données. Le système parcourt tous les fichiers `.txt` du répertoire `resources/prompts/system_prompts/` et compare leur contenu avec les enregistrements existants en base, via une empreinte SHA-256.

- Si un fichier n'a pas de ligne correspondante en base → insertion
- Si le contenu a changé (SHA différent) → mise à jour de la ligne et de l'horodatage
- Si une ligne en base n'a plus de fichier correspondant → la ligne est conservée (pour les logs historiques qui y font référence) avec un avertissement

Ce mécanisme garantit que la table `log_prompt` reflète toujours exactement les prompts en production. Chaque log de génération pointe vers la version précise du prompt qui a été utilisée, ce qui permet de reconstruire fidèlement a posteriori les conditions exactes d'une génération.

### 2.4 Chargement de la configuration à chaud

Les paramètres d'exploitation configurables (température LLM, seuil de template, nombre d'exemples RAG, etc.) sont stockés dans la table `app_setting`. Ils sont chargés en mémoire dans un cache en-process à ce stade, de sorte que tous les services puissent y accéder instantanément sans requête DB à chaque génération.

---

## 3. Le chemin arrière-plan : assets et données

### 3.1 Séquence de setup des assets

Le setup des assets suit une séquence linéaire de quatre étapes. Chaque étape conditionne la suivante : si le modèle d'embedding n'est pas disponible, les étapes qui nécessitent de vectoriser du texte sont sautées. Si la documentation PLaTon n'est pas téléchargée, la reconstruction des métadonnées de composants et l'indexation de la documentation sont sautées.

```
     [DÉMARRAGE ASSETS]
            │
     ┌──────▼───────┐
     │  ÉTAPE 1     │  Modèle d'embedding
     │  E5-large    │  Présent ? → continuer
     │              │  Absent   → télécharger depuis HuggingFace Hub
     └──────┬───────┘
            │ embedding_ready = True/False
     ┌──────▼───────┐
     │  ÉTAPE 2     │  Documentation PLaTon
     │  MDX files   │  Absente → télécharger depuis GitHub
     │  GitHub sync │  Présente, SHA inchangé → skip
     └──────┬───────┘  Présente, SHA changé → re-télécharger
            │ (docs_ready, docs_changed)
     ┌──────▼───────┐
     │  ÉTAPE 3     │  Métadonnées des composants
     │  metadata.   │  Absentes → construire depuis MDX
     │  json        │  Docs changées → reconstruire
     └──────┬───────┘  Présentes, docs inchangées → skip
            │
     ┌──────▼───────┐
     │  ÉTAPE 4     │  Table vectorielle documentation PLaTon
     │  Docs pgvec  │  (si docs_ready ET embedding_ready)
     │  table       │  Docs changées → reconstruire entièrement
     └──────────────┘  Table non-vide, docs inchangées → skip
```

### 3.2 Étape 1 — Le modèle d'embedding

Le modèle `intfloat/multilingual-e5-large-instruct` est le composant le plus lourd du système (~1.2 Go). Il est stocké localement dans `resources/local_models/`. Sa présence est vérifiée en regardant si le répertoire existe et contient les fichiers attendus.

Si le modèle est absent, il est téléchargé depuis HuggingFace Hub. Ce téléchargement est exécuté dans un thread séparé (`asyncio.to_thread`) pour ne pas bloquer la boucle d'événements principale pendant la durée du transfert.

**Scénario exceptionnel — modèle non disponible** : si le téléchargement échoue (HuggingFace inaccessible, espace disque insuffisant), `embedding_ready` est positionné à `False`. Toutes les fonctionnalités nécessitant les embeddings (RAG, vectorisation, recherche sémantique) sont désactivées pour ce démarrage. Un avertissement explicite est loggué : *"Restart the container once the model is accessible."* Le serveur reste fonctionnel pour les opérations ne nécessitant pas le RAG.

### 3.3 Étape 2 — La documentation PLaTon

La documentation officielle de PLaTon est hébergée sur GitHub (`PlatonOrg/platon`, branche `main`, sous-répertoire `apps/docs/`). Elle est composée de fichiers `.mdx` décrivant les composants, le langage PLE, les API, etc.

**Mécanisme de détection des changements** : l'API GitHub fournit un SHA de l'arbre Git pour le répertoire concerné. Ce SHA est comparé à une valeur stockée localement dans un fichier sentinelle (`.tree_sha`). Si les SHA sont identiques, aucune opération réseau n'est effectuée — la documentation locale est considérée à jour. Si les SHA diffèrent, les fichiers nouveaux ou modifiés sont téléchargés, les fichiers supprimés localement sont retirés, et le nouveau SHA est enregistré.

**Scénario exceptionnel — GitHub inaccessible** : si l'API GitHub ne répond pas au démarrage, le système utilise la copie locale existante telle quelle (aucune mise à jour). Si aucune copie locale n'existe du tout, `docs_ready` est positionné à `False` et les étapes dépendantes sont sautées.

**Scénario exceptionnel — Token GitHub absent** : sans token GitHub configuré, les requêtes sont anonymes, limitées à 60 requêtes par heure par l'API GitHub. Pour les déploiements production, il est recommandé de configurer un token via la variable d'environnement `GITHUB_TOKEN` pour bénéficier de 5000 requêtes par heure.

### 3.4 Étape 3 — Les métadonnées des composants

Les métadonnées des composants PLaTon sont générées automatiquement depuis les fichiers `.mdx` téléchargés. Le processus parse chaque fichier de composant pour en extraire :

- Le **tag** (identifiant technique, ex: `wc-input-box`) — extrait du premier identifiant préfixé `wc-` dans le fichier
- Le **nom** et la **description** — extraits du bloc frontmatter YAML en tête de fichier
- La **catégorie** — déduite du répertoire parent (`forms` → Formulaire, `widgets` → Widget)
- La **documentation** — texte de la section `## Documentation`
- Le **schéma de propriétés** — objet JSON extrait du composant `<ComponentProperties schema={...}/>`
- Le **chemin relatif** du fichier `.mdx` — pour une injection complète dans les prompts si nécessaire

Le résultat est sérialisé dans `resources/docs/components/metadata.json`. Ce fichier est la source de vérité du catalogue de composants, utilisé à la fois par les services backend (sélection de composants, construction des prompts) et par le frontend (affichage du catalogue).

La reconstruction n'a lieu qu'en cas de nécessité : si les docs viennent d'être mises à jour, ou si le fichier est absent. Dans tous les autres cas, le fichier existant est utilisé tel quel.

### 3.5 Étape 4 — Vectorisation de la documentation PLaTon

La documentation PLaTon est indexée dans une table pgvector dédiée pour alimenter la fonctionnalité de recherche documentaire (chat "Discussion"). Le processus transforme chaque fichier `.mdx` en texte brut (suppression du frontmatter, des blocs de code, des balises HTML, des directives d'import/export), puis découpe ce texte en chunks de ~900 caractères avec un chevauchement d'une phrase entre chunks consécutifs.

Chaque chunk est vectorisé par le modèle E5 et inséré dans pgvector comme un `TextNode` LlamaIndex portant ses métadonnées (chemin du fichier, position du chunk). Si la table est déjà peuplée et que les docs n'ont pas changé, cette étape est entièrement sautée. En cas de mise à jour de la documentation, la table est reconstruite entièrement.

---

## 4. La synchronisation des ressources PLaTon

C'est l'étape la plus longue et la plus spectaculaire de l'initialisation. Elle transforme une base de données vide en un index complet de toutes les ressources pédagogiques de PLaTon, prêtes pour la recherche sémantique.

### 4.1 Détection de l'état initial

La toute première question posée par le service de synchronisation est : **est-ce la première exécution ?** La réponse est déterminée en comptant les lignes dans les tables `exercise` et `template`. Si les deux sont vides, c'est une première exécution. Sinon, c'est une synchronisation delta depuis la dernière date enregistrée.

Cette distinction conditionne la stratégie de récupération des données depuis PLaTon : une première exécution déclenche une récupération exhaustive de tout le catalogue, tandis qu'une synchronisation delta ne récupère que les ressources modifiées depuis la dernière synchronisation.

```
Base vide ?
    │ Oui                              │ Non
    ▼                                  ▼
Récupération complète              Récupération delta
(tout le catalogue PLaTon)         (modifiés depuis last_sync)
```

### 4.2 Les quatre phases de la synchronisation

**Phase 1 — Synchronisation des composants**

Les métadonnées du catalogue de composants (issues de `metadata.json`) sont upsertées dans la table `component` de la base de données. Un upsert (INSERT ... ON CONFLICT DO UPDATE) garantit l'idempotence : si le composant existe déjà, ses champs sont mis à jour sans doublon. Cette phase est rapide (~30 composants à traiter).

**Phase 2 — Récupération du catalogue PLaTon**

Le client PLaTon est interrogé avec pagination pour récupérer toutes les ressources « prêtes » (*ready*). Deux catégories sont distinguées :
- Les **templates** (ressources configurables, `configurable=True`) — exercices paramétriques avec un fichier `main.plc`
- Les **exercices** (toutes les autres ressources prêtes) — exercices standalone ou basés sur un template

Les appels PLaTon transitent par le `CachedPlatonClient`, qui stocke les résultats dans Redis pour la durée du TTL configuré. Cela signifie que si le serveur redémarre peu après une synchronisation complète, les données PLaTon sont servies depuis Redis sans solliciter à nouveau l'API PLaTon.

**Phase 3 — Upsert en base de données**

Templates et exercices sont upsertés dans leurs tables respectives. Pour chaque exercice, le lien vers son template parent est établi si applicable. Les horodatages de création et de modification sont préservés depuis PLaTon, ce qui permettra aux synchronisations delta ultérieures de filtrer efficacement.

**Phase 4 — Liens entre ressources et composants**

Pour chaque exercice et chaque template synchronisé, le système récupère la liste des composants PLaTon qu'il utilise. Cette information est extraite en compilant la ressource via l'API PLaTon (`compile_resource_json`), qui retourne les variables effectives de l'exercice incluant les instances de composants.

Les liens sont stockés dans les tables `exercise_component_link` et `template_component_link`. Ces liens permettront ultérieurement de filtrer les ressources par composant dans l'interface d'administration.

Tous les appels à `compile_resource_json` bénéficient du cache Redis : la première synchronisation complète les peuple, et les synchronisations ultérieures ou les relances de vectorisation peuvent les réutiliser sans appels réseau supplémentaires.

### 4.3 Le démarrage en deux passes

Le démarrage initial effectue deux passes séparées plutôt qu'une seule, pour une raison précise :

```
PASSE 1 — Synchronisation DB (sync_vectors=False)
   PLaTon API → Redis cache → Tables exercise/template/component
   (Peuplage de la DB ET du cache Redis)

          ↓ DB peuplée, cache Redis peuplé

PASSE 2 — Vectorisation
   DB (exercices) → CachedPlatonClient (→ Redis, pas PLaTon) → Embeddings → pgvector
```

Cette séparation garantit que la vectorisation peut lire les données depuis la DB (nécessaire pour construire les nœuds à embedder) ET servir tous les appels PLaTon depuis le cache Redis plutôt que de solliciter à nouveau l'API. En production avec un catalogue de 200+ exercices, cela évite des centaines d'appels PLaTon redondants.

---

## 5. La vectorisation des exercices

### 5.1 Trois types de ressources, trois stratégies d'embedding

Toutes les ressources ne sont pas vectorisées de la même manière. Le contenu sémantique pertinent pour la recherche diffère selon le type :

**Exercice standalone** : le texte d'embedding combine les métadonnées (nom, description, niveaux scolaires, thèmes), les parties textuelles (titre, énoncé, formulaire) et un label de type. L'objectif est de capturer le sens pédagogique de l'exercice.

**Template** : en plus des métadonnées et des parties textuelles, les paramètres configurables du template (lus depuis `main.plc`) sont inclus. Chaque paramètre contribue avec son nom et sa description. Cela permet de retrouver un template dont les paramètres correspondent à la demande, même si le titre ne correspond pas exactement.

**Exercice basé sur un template (TEMPLATE_EXO)** : c'est le cas le plus riche. Le texte d'embedding fusionne les valeurs concrètes de l'exercice (lues depuis `main.plo`) avec les descriptions sémantiques des paramètres correspondants (lues depuis `main.plc` du template parent). Résultat : chaque instance de template est indexée avec sa valeur réelle *et* la description de ce que cette valeur représente.

Exemple : si un template a un paramètre `question` (description : "la question posée à l'étudiant") et qu'une instance a `question="Calculez la dérivée de..."`, le texte d'embedding contient *"question: [la question posée à l'étudiant] → Calculez la dérivée de..."* — ce qui rend la recherche sémantique sur le contenu mathématique possible même pour des exercices basés sur des templates.

### 5.2 Construction et commit des vecteurs

Pour chaque ressource à vectoriser, le système :

1. Récupère les métadonnées depuis PLaTon (via le cache Redis)
2. Compile les variables de la ressource (via le cache Redis)
3. Lit les fichiers de configuration si nécessaire (`.plc`, `.plo`) (via le cache Redis)
4. Construit le texte d'embedding selon la stratégie du type
5. Génère le vecteur de 1024 dimensions avec le modèle E5 local
6. Crée un `TextNode` LlamaIndex portant le texte, l'embedding et les métadonnées (db_id, platon_id, name, kind)

Tous les nœuds construits sont ensuite committé en base vectorielle pgvector en une seule passe. Pour une première installation (table vide), LlamaIndex crée l'index entier. Pour une synchronisation incrémentale, les nœuds sont ajoutés directement avec `vector_store.add(nodes)`.

Une barre de progression en terminal affiche l'avancement en temps réel dans les logs Docker :

```
  [████████████████░░░░░░░░░░░░░░]  52/120 (43%)  EXERCICE     3f8a1b2c…  1.24s
  ✓ [████████████████░░░░░░░░░░░░░░]  53/120 (44%)  TEMPLATE     7d2e9f01…  0.87s
  ✗ [████████████████░░░░░░░░░░░░░░]  54/120 (45%)  TEMPLATE_EXO a1b2c3d4…  0.12s  (échec)
```

### 5.3 La synchronisation quotidienne

Une fois l'initialisation terminée, une tâche de fond se réveille toutes les 24 heures et exécute une synchronisation delta. Elle récupère uniquement les ressources PLaTon modifiées depuis la dernière synchronisation réussie (horodatage stocké dans la table `sync_tracker`), les upserte en DB, et met à jour leurs vecteurs. Seules les ressources qui ont changé sont re-vectorisées.

---

## 6. Scénarios exceptionnels et leur gestion

### 6.1 Installation complètement vierge

C'est le scénario de premier déploiement. Aucune table n'existe, aucun asset n'est présent.

```
Démarrage →
  Chemin critique :
    Toutes les tables créées depuis zéro ✓
    Aucune migration à appliquer (version 0 → LATEST_VERSION) ✓
    Prompts synchronisés ✓
  Arrière-plan :
    Modèle E5 téléchargé depuis HuggingFace (~1.2 Go, quelques minutes) ✓
    Documentation PLaTon téléchargée depuis GitHub (~200 fichiers MDX) ✓
    Métadonnées de composants construites depuis les MDX ✓
    Documentation vectorisée (~1500 chunks) ✓
    Authentification admin PLaTon ✓
    Catalogue complet récupéré (ex: 150 exercices, 20 templates) ✓
    DB peuplée, cache Redis peuplé ✓
    150 exercices + 20 templates vectorisés ✓
```

L'API est opérationnelle pour les requêtes non-RAG dès les premières secondes. Les fonctionnalités RAG sont disponibles une fois le modèle chargé et la vectorisation terminée (typiquement 5 à 20 minutes selon la machine et la taille du catalogue).

### 6.2 Ajout d'un seul exercice dans PLaTon

C'est le scénario standard de maintenance. Un enseignant ou un administrateur ajoute un exercice sur PLaTon, et veut qu'Agora le prenne en compte lors de la prochaine génération.

La synchronisation quotidienne ou le prochain redémarrage du service suffit. Le delta détecte l'exercice nouvellement ajouté (son horodatage est postérieur à la dernière synchronisation), l'upserte dans la table `exercise`, récupère ses composants depuis l'API PLaTon (via cache Redis si disponible), établit les liens, construit son embedding et l'ajoute à la table vectorielle.

À l'issue de ce cycle, l'exercice est indexé et sera retourné par les recherches RAG correspondant à son contenu pédagogique.

### 6.3 Redémarrage avec un catalogue déjà indexé

C'est le scénario de redémarrage courant (mise à jour du code, rechargement de config).

```
Démarrage →
  Chemin critique : rapide (~quelques secondes)
    Tables déjà existantes → aucune création
    Schema à jour → aucune migration
    Prompts : SHA identiques → aucune mise à jour
    Config chargée depuis DB ✓
  Arrière-plan :
    Modèle E5 : déjà présent → aucun téléchargement ✓
    Documentation PLaTon : SHA GitHub identique → aucun téléchargement ✓
    Métadonnées composants : présentes, docs inchangées → skip ✓
    Docs vectorisées : table non-vide, docs inchangées → skip ✓
    Cache Redis : peuplé dans le TTL → appels PLaTon servis depuis cache ✓
    Synchronisation delta : seules les ressources nouvelles/modifiées ✓
```

Un redémarrage type prend moins d'une minute avant que le service soit entièrement opérationnel, toutes fonctionnalités incluses.

### 6.4 Mise à jour d'un prompt système

Un opérateur modifie un fichier `.txt` dans `resources/prompts/system_prompts/` et redémarre le service (ou attend si le rechargement à chaud est activé).

Au prochain démarrage, la synchronisation des prompts détecte le SHA différent et met à jour la ligne en base. Le nouveau prompt est utilisé immédiatement pour toutes les générations suivantes. Les logs de générations précédentes conservent toujours une référence à l'ancienne version du prompt (la ligne en base n'est pas supprimée, seulement mise à jour).

### 6.5 PLaTon inaccessible au démarrage

Si l'authentification admin vers PLaTon échoue, la synchronisation est entièrement sautée avec un message d'erreur. Les données déjà en base (issues des synchronisations précédentes) restent disponibles. Le RAG continue de fonctionner sur le catalogue existant. La prochaine synchronisation réussira lors du redémarrage suivant ou lors du prochain cycle quotidien.

### 6.6 Table vectorielle avec des données mais sans enregistrement de sync

Ce cas peut se produire si un opérateur peuple manuellement la table vectorielle ou si le registre de synchronisation est corrompu. Le service détecte que la table contient des lignes mais qu'aucun horodatage de synchronisation n'est enregistré. Il considère la table à jour, enregistre l'horodatage courant, et ne fait rien — évitant une re-vectorisation complète non nécessaire.

---

## 7. Tableau récapitulatif des conditions de déclenchement

| Opération | Condition de déclenchement | Condition de skip |
|---|---|---|
| Création de tables | Démarrage, tables manquantes | Tables déjà existantes |
| Migration de schéma | Version DB < LATEST_VERSION | Version DB = LATEST_VERSION |
| Sync des prompts | Fichier absent ou SHA différent | SHA identique |
| Téléchargement modèle E5 | Répertoire du modèle absent | Modèle déjà présent |
| Téléchargement docs PLaTon | Absent OU SHA GitHub différent | SHA identique (1 appel API) |
| Rebuild metadata.json | Absent OU docs viennent d'être mises à jour | Présent + docs inchangées |
| Vectorisation docs | Table vide OU docs viennent d'être mises à jour | Table non-vide + docs inchangées |
| Sync ressources PLaTon (full) | Tables exercise et template vides | DB déjà peuplée |
| Sync ressources PLaTon (delta) | DB peuplée, chaque démarrage + quotidien | Aucun (toujours exécutée, peut être vide) |
| Vectorisation exercices (full) | Table vectorielle vide | Table non-vide |
| Vectorisation exercices (delta) | Ressources ajoutées/modifiées depuis last_sync | Aucune ressource nouvelle |

---

*Document établi le 9 mars 2026 — source de vérité : code source de l'application.*

