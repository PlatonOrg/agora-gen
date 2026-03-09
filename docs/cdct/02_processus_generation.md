# Cahier des Charges Technique — Agora AI Agent
## Partie II : Le Processus de Génération d'Exercices

---

## Préambule

Ce document décrit le processus de génération d'exercices PLaTon au sein du système Agora. Il adopte une perspective fonctionnelle et architecturale : ce qui se passe, pourquoi, quelles données circulent entre les composants, et quelles décisions sont prises à chaque carrefour. Il ne décrit pas les détails d'implémentation mais le comportement observable du système et la logique qui le gouverne.

La génération d'exercice est le cœur fonctionnel d'Agora. Elle se déclenche lorsqu'un enseignant soumet une demande textuelle en langage naturel depuis l'interface de conversation. Ce processus mobilise en séquence la recherche sémantique, la sélection de composants par IA, la génération de code par un grand modèle de langage, puis la validation par un sandbox d'exécution réel. L'ensemble se déroule de manière asynchrone et communique en temps réel avec le client via un flux d'événements continus (Server-Sent Events).

---

## 1. Nature de la communication client-serveur

La génération n'est pas un simple appel HTTP requête/réponse. C'est un flux continu de type SSE (*Server-Sent Events*). Dès que la requête est reçue, le serveur commence à émettre des événements de progression nommés au fil de l'exécution. Le client les consomme en temps réel pour mettre à jour l'interface : chaque étape franchie est signalée avec un label et, le cas échéant, des données structurées (liste de composants sélectionnés, ressources RAG retrouvées, URL de prévisualisation...).

Ce choix architectural permet à l'enseignant de voir le système « penser » en direct, plutôt que d'attendre une réponse opaque dont on ignore la durée. En cas d'échec partiel (par exemple, un retry sandbox), l'événement correspondant est également émis, ce qui permet au frontend d'afficher un état de correction en cours.

La requête entrante porte les données suivantes :

| Donnée | Rôle |
|---|---|
| Message de l'enseignant | L'instruction en langage naturel |
| État courant de l'exercice | Sérialisation complète de l'exercice en cours d'édition |
| Historique de la conversation | Les échanges précédents de la session |
| Composants choisis par l'utilisateur | Tags de composants PLaTon sélectionnés manuellement |
| Fichiers joints | Identifiants Redis de fichiers uploadés + leurs résumés |
| Champs à modifier | En cas de modification ciblée, liste des seuls champs à régénérer |
| Indicateur de mode forcé | Si positionné, court-circuite la sélection de template |

---

## 2. La décision initiale : première génération ou modification ?

Avant toute chose, le système doit déterminer s'il fait face à une première génération ou à une modification d'un exercice existant. Cette décision conditionne l'intégralité du chemin suivi ensuite.

La règle est simple et entièrement pilotée par les données : si l'état de l'exercice envoyé dans la requête est vide (aucun titre, aucun code, aucun contenu), c'est une première génération. Sinon, c'est une modification. Il n'y a aucun état de session côté serveur qui influence cette décision — elle est **sans état** (*stateless*), ce qui la rend robuste et prévisible, même si l'utilisateur ferme l'onglet et revient plus tard.

En cas de modification, le mode de génération utilisé initialement est également verrouillé : un exercice basé sur un template PLaTon restera en mode template pour toutes ses modifications ultérieures. Un exercice généré en mode pur restera en mode pur. Cette cohérence est garantie par le contenu même de l'état de l'exercice — la présence ou l'absence de variables de configuration de template.

```
┌─────────────────────────────────────────────────────────────────┐
│               Requête de génération reçue                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   L'exercice est-il vide ?   │
              └──────┬───────────────┬───────┘
                     │ Oui           │ Non
                     ▼               ▼
             Première          Modification
             génération        (mode verrouillé
                                par l'état de
                                l'exercice)
```

---

## 3. La recherche sémantique (RAG)

La recherche RAG (*Retrieval-Augmented Generation*) n'est effectuée que pour une première génération. Pour les modifications, elle est ignorée car les ressources de référence sont déjà intégrées dans l'exercice existant.

### Objectif dual

La recherche sert deux objectifs distincts en une seule passe :

1. **Trouver un template réutilisable** : si une ressource PLaTon de type « template » présente une similarité suffisamment élevée avec la demande, il est plus efficace de remplir ses paramètres configurables que de tout régénérer depuis zéro.

2. **Constituer un corpus d'exemples** : les exercices les plus proches de la demande seront injectés dans le prompt de génération comme exemples concrets à imiter.

### Comment la recherche fonctionne

La requête de recherche est construite en combinant le message de l'enseignant et les tags de composants déjà présents dans l'exercice. Elle est transformée en vecteur dense de 1024 dimensions par le modèle d'embedding multilingue hébergé localement (`intfloat/multilingual-e5-large-instruct`). Ce vecteur est comparé par similarité cosinus à l'ensemble des ressources indexées dans la base vectorielle pgvector.

Les résultats retournés sont des paires (ressource PLaTon, score de similarité). Le score est un réel entre 0 et 1. Le nombre de résultats récupérés est le maximum entre le nombre de résultats à logger et le nombre d'exemples souhaités dans le prompt — ce qui garantit qu'aucune des deux contraintes ne tronque l'autre.

Chaque résultat porte les métadonnées de la ressource PLaTon associée : son identifiant, son nom, son type (exercice ou template), et l'identifiant de son vecteur en base.

---

## 4. La bifurcation template / exercice pur

C'est le carrefour stratégique du processus. Le système examine les résultats de la recherche pour décider de la stratégie de génération.

### Le critère de sélection d'un template

Un template est sélectionné si et seulement si le meilleur candidat de type « template » dans les résultats dépasse un seuil de score configurable (`TEMPLATE_SCORE_THRESHOLD`, valeur par défaut 0.85). Ce seuil représente un degré de confiance élevé : on ne veut pas qu'un template vaguement proche soit utilisé et produise un exercice hors sujet.

Si le seuil est franchi, le système récupère depuis PLaTon le fichier de configuration du template. Ce fichier JSON décrit les variables paramétrables du template : leur nom, leur type (texte, nombre, liste, sélection...), leur description sémantique et leur valeur par défaut. C'est ce schéma qui pilotera entièrement la génération LLM dans la voie template.

### Les deux voies possibles

```
             Résultats RAG
                   │
     ┌─────────────▼──────────────┐
     │  Meilleur template         │
     │  score >= seuil (0.85) ?   │
     └────────┬────────────┬──────┘
              │ Oui        │ Non
              ▼            ▼
        VOIE TEMPLATE   VOIE EXERCICE PUR
        Remplissage     Génération libre
        des paramètres  de tout le code
        du template     de l'exercice
```

---

## 5. Voie Exercice Pur — Sélection des composants

Cette étape est spécifique à la voie exercice pur, pour une première génération uniquement.

### Pourquoi cette étape existe

Les composants PLaTon (`wc-input-box`, `wc-math-live`, `wc-drag-drop`, `wc-matrix`, etc.) sont les briques visuelles et interactives de l'exercice. Ils doivent être connus avant que le LLM génère le code, car ce dernier doit les initialiser dans le builder et les lire dans le grader selon des conventions strictes propres à chaque composant. Une mauvaise sélection de composants conduit à un exercice inutilisable.

### Le processus de sélection

Un LLM dédié reçoit la liste des composants disponibles avec leur description courte, la demande de l'enseignant, et la documentation complète des composants déjà choisis explicitement par l'enseignant. Il retourne une réponse structurée contenant deux champs :

- **`reasoning`** : une justification textuelle de la sélection, expliquant comment les composants retenus répondent à la demande pédagogique.
- **`selected_tags`** : la liste ordonnée des identifiants de composants sélectionnés, contrainte par un schéma JSON à n'émettre que des valeurs figurant dans la liste des composants disponibles.

La liste finale combine les composants choisis par l'enseignant (prioritaires, toujours inclus sans exception) et les composants sélectionnés par le LLM. Cette distinction est conservée dans les logs et transmise à l'étape de génération : les composants imposés par l'enseignant reçoivent une documentation complète dans le prompt de génération, tandis que les composants sélectionnés par le LLM sont présentés en contexte indicatif.

---

## 6. Voie Exercice Pur — Constitution du corpus d'exemples

En parallèle de la sélection de composants, le système constitue un corpus d'exemples concrets à injecter dans le prompt de génération.

Pour chacun des exercices les mieux classés par la recherche RAG (jusqu'à `NUM_EXAMPLE_EXERCISES` exemples), le système récupère depuis PLaTon les variables compilées de la ressource. Ces variables représentent l'état complet de l'exercice tel qu'il existe réellement sur PLaTon : titre, code builder, code grader, metadata pédagogique, etc. Pour les ressources de type template, les paramètres configurables sont également inclus.

Ces exemples sont tronqués si nécessaire pour ne pas dépasser la fenêtre de contexte du LLM, puis injectés directement dans le prompt système en tant que *few-shot examples*. Leur rôle est de « montrer » au LLM le style, la structure et le niveau de détail attendus dans l'exercice à générer.

---

## 7. La génération LLM

C'est l'étape centrale du processus. Le LLM reçoit un contexte soigneusement assemblé et produit soit l'intégralité du code de l'exercice (voie pure), soit les valeurs des paramètres du template (voie template).

### Composition du contexte

Le contexte envoyé au LLM est construit en deux parties, prompt système et prompt utilisateur, assemblées selon une logique précise.

**Le prompt système** est un fichier texte versionné, stocké dans le répertoire `resources/prompts/`. Il existe une variante par scénario : première génération, modification, génération en mode template, modification en mode template, correction d'erreur sandbox. Ces fichiers constituent la « personnalité » du modèle pour chaque cas d'usage. En mode première génération pure, les exemples d'exercices récupérés par RAG y sont concaténés.

**Le prompt utilisateur** est assemblé dynamiquement à chaque requête. Il contient dans l'ordre :
1. La documentation des composants sélectionnés, avec une distinction claire entre composants obligatoires (imposés par l'enseignant, documentation complète) et composants indicatifs (sélectionnés par le LLM, contexte historique)
2. L'état courant de l'exercice sérialisé en JSON, avec les noms de champs canoniques attendus en sortie
3. L'historique des échanges de la conversation, pour maintenir la cohérence sur plusieurs tours
4. La demande de l'enseignant
5. Le contenu textuel des fichiers joints, si présents

### La contrainte de format de sortie

Le LLM ne retourne pas du texte libre : il est contraint à émettre un objet JSON conforme à un schéma strict. Ce schéma est adapté dynamiquement selon le scénario :

- En **mode exercice pur**, le schéma impose les champs `name`, `description`, `title`, `sandbox` (valeur contrainte à `"node"` ou `"python"`), `builder`, `grader`, `statement`, `form`, `solution`, et un objet `metadata` contenant obligatoirement `levels` et `topics`. Les champs additionnels sont autorisés pour les variables sandbox supplémentaires.

- En **mode template**, le schéma est construit dynamiquement à partir du fichier de configuration du template. Chaque variable du template devient une propriété typée dans le schéma (texte, nombre, booléen, liste, sélection avec enum...).

- Pour la **sélection de composants**, le schéma impose uniquement `reasoning` (texte libre) et `selected_tags` (tableau dont chaque élément est contraint à être l'un des identifiants de composants disponibles), sans propriétés additionnelles.

Le schéma est transmis au provider LLM selon son format propre (Cerebras, OpenRouter, Gemini, Ollama ont chacun leur convention d'enveloppe). En cas de réponse non conforme au JSON attendu (ce qui peut arriver avec certains providers ou dans des situations de contexte long), le système tente une chaîne de stratégies de récupération : parsing direct, extraction depuis un bloc de code markdown, réparation d'un JSON tronqué, extraction par appariement d'accolades.

### Métriques de consommation

À chaque appel LLM, les métriques de consommation de tokens (entrée et sortie) sont enregistrées. Cela couvre non seulement l'appel principal de génération, mais aussi les appels de sélection de composants et les éventuels appels de correction d'erreur sandbox. L'ensemble est consolidé et stocké dans les logs de génération.

---

## 8. Désinfection de la sortie LLM

Avant d'être envoyé au sandbox, l'exercice généré passe par une couche de nettoyage automatique. Cette étape existe parce que les LLM produisent parfois des sorties syntaxiquement incorrectes qui feraient échouer le sandbox sans que ce soit une erreur de logique : séquences d'échappement mal placées (`\n` littéral dans du code Python), propriétés de feedback mal nommées, composants référencés dans le code sans être déclarés dans la liste des composants de l'exercice.

Le nettoyage distingue les champs texte (title, statement, form, solution) des champs code (builder, grader) : dans les champs code, les désescapements sont appliqués de manière chirurgicale pour ne pas altérer les chaînes de caractères intentionnelles du code Python. Une compilation syntaxique préventive est également réalisée localement avant d'envoyer au sandbox distant — ce qui permet de détecter les erreurs de syntaxe Python sans consommer une requête réseau.

---

## 9. La validation par le sandbox PLaTon

La validation sandbox est la dernière étape de vérification avant que l'exercice soit présenté à l'enseignant. C'est le seul moyen fiable de savoir si le code généré fonctionne réellement, car l'environnement d'exécution PLaTon a ses propres conventions et ses propres dépendances.

### Deux vérifications distinctes

La validation se déroule en deux temps séquentiels :

**Vérification du builder** : le fichier PLE complet est soumis à PLaTon, qui crée une ressource de prévisualisation éphémère et l'exécute. Cette exécution déclenche le code du builder — le code Python ou JavaScript qui initialise les composants, génère les valeurs aléatoires, et construit l'état de l'exercice. Si cette exécution produit des erreurs (runtime Python, noms de variables non définis, erreurs d'attribut...) elles sont remontées dans les logs de la ressource PLaTon.

**Vérification du grader** : avec la session créée à l'étape précédente, une évaluation simulée est déclenchée avec une réponse vide. Cela exécute le code du grader — le code qui corrige la réponse de l'étudiant. Tester le grader sans réponse permet de détecter les erreurs d'initialisation et les références à des variables que le builder aurait dû définir.

Ces deux vérifications sont intentionnellement séparées parce que les erreurs du builder et du grader ont des causes différentes et nécessitent des corrections différentes.

### Données échangées avec PLaTon

```
┌──────────────────────────────────────────────────────────────┐
│  Agora → PLaTon                                              │
│  POST /resources/preview                                     │
│  { "files": [{ "path": "main.ple", "content": "..." }] }    │
└──────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  PLaTon → Agora                                              │
│  { "resource_id": "...", "session_id": "...",                │
│    "platon_logs": [{ "type": "error|info", "message": ... }] }│
└──────────────────────────────────────────────────────────────┘
```

Une réponse HTTP 200 ne suffit pas à valider l'exercice : PLaTon peut retourner HTTP 200 tout en reportant des erreurs d'exécution dans les logs. Le système inspecte systématiquement les logs pour détecter les entrées de type `"error"`.

---

## 10. La boucle de correction automatique

### Principe

Lorsque le sandbox rejette l'exercice — que ce soit une erreur de syntaxe, une erreur d'exécution du builder, ou une erreur d'exécution du grader — le système ne renvoie pas immédiatement un échec à l'enseignant. Il tente de corriger le problème automatiquement en soumettant l'exercice défaillant et le message d'erreur à un LLM de réparation spécialisé.

### Le cycle de retry

```
          Exercice généré
               │
               ▼
        Vérification sandbox
               │
      ┌────────┴────────┐
      │ Succès          │ Échec (erreur sandbox)
      ▼                 ▼
   Terminé         LLM de réparation
                   (prompt repair + erreur + code actuel)
                        │
                        ▼
               Code corrigé en place
                        │
                        ▼
               Vérification sandbox (tentative N+1)
               (jusqu'à SANDBOX_RETRY_MAX_ATTEMPTS)
```

Le LLM de réparation reçoit : le type d'erreur (`"compilation"`, `"runtime"`, `"grader_runtime"`), le message d'erreur exact, le code courant de l'exercice en JSON, et optionnellement la documentation officielle du langage PLaTon (activable via le paramètre `REPAIR_INJECT_PLE_DOCS`). Il retourne l'exercice complet corrigé, selon le même schéma JSON que la génération initiale.

En cas d'échec de la correction LLM elle-même (exception réseau, réponse invalide), la boucle s'arrête immédiatement — le nombre total de tentatives sandbox est limité par `SANDBOX_RETRY_MAX_ATTEMPTS` et le timeout global par `SANDBOX_RETRY_TIMEOUT_SECONDS`.

### Ce que le retry signifie pour les statistiques

Le système distingue trois issues possibles d'une génération :

- **Succès immédiat** : le sandbox valide l'exercice dès la première tentative.
- **Succès après correction** : le sandbox a échoué au moins une fois, mais la correction automatique a résolu le problème.
- **Échec définitif** : toutes les tentatives ont échoué, l'exercice est retourné à l'enseignant avec le dernier message d'erreur.

---

## 11. La journalisation structurée

Chaque génération est enregistrée de manière non-bloquante dans PostgreSQL, quelles que soient son issue et sa voie. L'enregistrement est asynchrone et découplé de la réponse SSE : il ne ralentit jamais l'expérience utilisateur.

### Modèle de données de log

Les données de log sont organisées autour de quatre entités principales :

**La requête** capture le contexte d'entrée : message de l'enseignant, historique de la conversation, état de l'exercice au moment de la demande, noms et résumés des fichiers joints, et les champs ciblés en cas de modification.

**La recherche RAG** capture les résultats de la recherche sémantique : le modèle d'embedding utilisé, la table vectorielle interrogée, la requête construite, et pour chaque résultat retourné son rang, son identifiant PLaTon, son type et son score de similarité.

**La sélection de composants** (voie pure uniquement) capture le raisonnement LLM, les composants imposés par l'enseignant, les composants sélectionnés par le LLM, et les métriques de tokens de cet appel spécifique.

**Le résultat de génération** capture la sortie brute du LLM (avant parsing), la sortie parsée, le provider et le modèle utilisés, les métriques de tokens (entrée, sortie, nombre d'appels détaillés par type), l'URL de prévisualisation en cas de succès, le nombre de retries et les erreurs rencontrées, et le statut final (`completed`, `failed`, `error`).

Ces quatre entités sont reliées à une **conversation** (qui regroupe plusieurs générations successives sur un même exercice) et portent l'identifiant de la session et le nom d'utilisateur pour permettre les agrégations statistiques.

### La notion de conversation

Une conversation regroupe toutes les générations effectuées au sein d'une même session de travail sur un exercice. Elle est identifiée par un `conversation_id` généré côté frontend et transmis dans chaque requête. Plusieurs modifications successives d'un même exercice appartiennent toutes à la même conversation.

---

## 12. Paramètres opérationnels configurables

Tous les paramètres suivants sont modifiables en temps réel depuis l'interface d'administration, sans redémarrage du service. Ils sont persistés en base de données et lus à chaque génération.

| Paramètre | Valeur par défaut | Rôle |
|---|---|---|
| Température de génération | 0.0 | Déterminisme du LLM (0 = déterministe, valeurs plus élevées = plus de créativité) |
| Nombre d'exemples | 10 | Nombre d'exercices similaires injectés dans le prompt |
| RAG top-K (log) | 10 | Nombre de résultats RAG enregistrés dans les logs |
| Tentatives sandbox max | 3 | Nombre de cycles correction → vérification avant abandon |
| Timeout sandbox | 120 s | Durée maximale de la boucle de retry |
| Seuil de sélection template | 0.85 | Score de similarité minimum pour activer la voie template |
| Documentation PLaTon en réparation | Non | Injection du langage PLaTon dans le prompt de correction |

---

## 13. Flux de données de bout en bout

Le diagramme suivant synthétise l'ensemble des flux de données entre les composants du système pour une première génération en mode exercice pur.

```
Enseignant
    │  Message + état exercice (vide)
    ▼
Interface Angular
    │  POST /api/v1/chat/
    │  { user_request, exercise_state, conversation_history, ... }
    ▼
API Backend (FastAPI)
    │  Flux SSE ouvert
    │
    ├──▶ Base vectorielle pgvector
    │        Requête : vecteur E5 de la demande
    │        Réponse : N ressources PLaTon + scores
    │
    ├──▶ API PLaTon (si template sélectionné)
    │        Requête : GET fichier main.plc du template
    │        Réponse : schéma JSON des variables configurables
    │
    ├──▶ LLM de sélection de composants
    │        Entrée : liste composants + demande
    │        Sortie : { reasoning, selected_tags }
    │
    ├──▶ API PLaTon (pour les exemples)
    │        Requête : compilation de chaque exercice exemple
    │        Réponse : variables compilées de l'exercice
    │
    ├──▶ LLM de génération (principal)
    │        Entrée : prompt système + exemples + composants + historique
    │        Sortie : JSON complet de l'exercice selon schéma contraint
    │
    ├──▶ API PLaTon (validation builder)
    │        Entrée : fichier PLE complet
    │        Sortie : resource_id + session_id + platon_logs
    │
    ├──▶ API PLaTon (validation grader)
    │        Entrée : session_id + réponse vide
    │        Sortie : platon_logs du grader
    │
    │  [si erreur sandbox : itération LLM de correction jusqu'à N fois]
    │
    ├──▶ PostgreSQL (journalisation asynchrone)
    │        Requête, RAG, sélection, résultat, conversation
    │
    └──▶ Interface Angular
             Événement SSE final : exercice complet + URL preview
    ▼
Enseignant
    Voit l'exercice dans l'éditeur, peut le tester sur PLaTon Player
```

---

## 14. Exemple concret : du message à l'exercice

Pour ancrer les sections précédentes dans la réalité, voici une trace complète d'une génération aboutie.

---

**Demande de l'enseignant :** *« Crée un exercice de mathématiques sur les nombres premiers pour des élèves de lycée. L'étudiant doit trouver le plus petit diviseur d'un entier. »*

**Événement 1 — Démarrage de la recherche**
Le système construit la requête de recherche, la vectorise, et interroge pgvector. Il reçoit 10 ressources en retour. Le meilleur résultat de type exercice a un score de 0.78, le meilleur de type template a un score de 0.71. Aucun ne dépasse le seuil de 0.85. Le mode exercice pur est sélectionné.

**Événement 2 — Sélection des composants**
Le LLM de sélection reçoit les 32 composants disponibles et la demande. Il sélectionne `wc-input-box` pour la saisie d'un entier et retourne le raisonnement : *« La demande requiert la saisie d'une valeur numérique entière. Le composant `wc-input-box` configuré en mode numérique est le choix minimal et adéquat. »*

**Événement 3 — Génération LLM**
Le prompt assemblé fait environ 14 000 tokens (prompt système incluant les 2 exercices exemples les plus proches, documentation du composant, demande de l'enseignant). Le LLM consomme 4 200 tokens en entrée et produit 820 tokens en sortie. Il retourne un objet JSON valide contenant le nom, le titre, le builder Python (génération d'un entier aléatoire, calcul du plus petit diviseur, initialisation du composant `input_box`), le grader (lecture de la valeur saisie, comparaison, attribution du grade), et les métadonnées pédagogiques.

**Événement 4 — Validation sandbox**
Le fichier PLE est soumis à PLaTon. Builder : aucune erreur dans les logs, `resource_id` obtenu. Grader : aucune erreur avec une réponse vide. L'URL de prévisualisation est retournée.

**Événement 5 — Terminé**
Aucun retry nécessaire. L'exercice est retourné à l'enseignant. Dans les logs, `retry_count` est nul (aucun retry). La statistique « génération sans erreur » est incrémentée.

---

*Document établi le 9 mars 2026 — source de vérité : code source de l'application.*
