# Manuel Utilisateur — Agora AI Agent

## 1. Introduction

Agora est un outil permettant aux enseignants de créer des exercices PLaTon à l'aide d'un assistant IA conversationnel. L'outil propose deux modes de fonctionnement :

- **Mode Générer** : Création et modification d'exercices PLaTon via l'IA
- **Mode Discuter** : Questions/réponses sur la documentation PLaTon

---

## 2. Connexion

1. Accédez à l'URL de l'application Agora
2. Cliquez sur **Se connecter** pour être redirigé vers PLaTon
3. Authentifiez-vous avec vos identifiants PLaTon
4. Vous serez redirigé vers l'espace de travail

---

## 3. Espace de travail

### 3.1 Zone de discussion (panneau gauche)

Le panneau de discussion permet de communiquer avec l'assistant IA.

#### Mode Générer
- Décrivez l'exercice souhaité en langage naturel
- L'assistant génère le code PLaTon correspondant
- Vous pouvez modifier l'exercice via des instructions complémentaires

#### Mode Discuter
- Posez des questions sur PLaTon ou la documentation
- L'assistant recherche dans la documentation et répond

#### Actions disponibles
- **Glisser-déposer** un composant, champ ou paramètre dans le chat pour le référencer
- **Joindre un fichier** (icône trombone) : textes uniquement (pas de binaires). Le fichier est traité et résumé pour le contexte
- **Arrêter** : Cliquez sur le bouton stop pendant une génération pour l'interrompre
- **Effacer la conversation** : Réinitialise l'historique de discussion

#### Fichiers joints
- Maximum de fichiers configurable (par défaut : 5)
- Seuls les documents textuels sont acceptés (pas de fichiers binaires)
- Un indicateur de chargement apparaît pendant le traitement du fichier
- Pour annuler un fichier, cliquez sur le × du badge — le fichier est retiré côté serveur

#### Mode exercice pur
- Avant la première génération, vous pouvez activer le mode « exercice pur » pour forcer la génération sans template

### 3.2 Zone d'exercice (panneau droit)

L'éditeur affiche et permet de modifier le contenu de l'exercice :

| Onglet | Contenu |
|--------|---------|
| **Contenu** | Titre, énoncé, forme, solution, sandbox |
| **Composants** | Composants PLaTon utilisés (formulaires, widgets) |
| **Optionnel** | Indications, théories |
| **Technique** | Code builder, code grader |
| **Paramètres** | Variables de configuration du template |
| **Métadonnées** | Niveaux, thématiques, readme |

### 3.3 Prévisualisation

- **Voir exercice** : Compile et affiche l'exercice dans le sandbox PLaTon
- **Voir PLE** : Affiche le fichier PLE brut

### 3.4 Publication

1. Cliquez sur **Publier** dans la barre d'outils
2. Sélectionnez le cercle de destination (vous devez avoir les droits d'écriture)
3. Choisissez le statut (Prêt à l'emploi, Brouillon, Non testé, Bugué)
4. Confirmez — un indicateur de chargement apparaît pendant la publication

---

## 4. Journaux (Logs)

### 4.1 Conversations

- Liste de toutes les conversations enregistrées
- Chaque conversation regroupe les générations d'exercices et discussions effectuées
- **Filtrer** : par texte (barre de recherche), par date (sélecteur de période), et par tri
- **Supprimer** : Cliquez sur l'icône poubelle pour supprimer une conversation (y compris les conversations orphelines)
- **Détail** : Cliquez sur une conversation pour voir ses générations
- **Détail d'une génération** : Cliquez sur une génération dans la liste pour accéder à sa page de détails

### 4.2 Détails d'une génération

La page de détail d'une génération est structurée en sections :

1. **Entrées utilisateur** : Message, composants, champs, fichiers joints (résumé), historique de conversation
2. **État de l'exercice** : L'état de l'exercice au moment de la requête (repliable)
3. **Recherche RAG** : Résultats de la recherche vectorielle, scores de similarité
4. **Sélection de composants** : Raisonnement du LLM pour le choix des composants
5. **Génération LLM** : Prompt système, sortie LLM, tentatives de correction avec classification des erreurs (syntaxe, builder, grader, sandbox), consommation de tokens

---

## 5. Configuration (Administration)

### 5.1 Fournisseur LLM actif

Sélectionnez le fournisseur et le modèle LLM utilisés pour la génération. La modification prend effet immédiatement.

### 5.2 Paramètres de génération

Configurez les paramètres runtime sans redémarrer le serveur :

- **Température** : Contrôle la créativité du LLM (0.0 = déterministe)
- **Exercices exemples** : Nombre d'exercices du RAG utilisés comme exemples
- **Tentatives sandbox** : Nombre max de corrections automatiques
- **Fichiers joints max** : Limite de fichiers par session
- **Seuil de score template** : Score minimum pour utiliser un template existant
- **Niveau de log** : DEBUG, INFO, WARNING, ERROR

### 5.3 Modèle d'embedding

Affiche le nom du modèle d'embedding utilisé pour la recherche vectorielle (non modifiable dynamiquement).

---

## 6. Tableau de bord (Statistiques)

Le tableau de bord administrateur présente les métriques du système :

| Métrique | Description |
|----------|-------------|
| **Conversations** | Nombre total de conversations (chaque conversation = un ou plusieurs échanges) |
| **Exercices publiés** | Nombre d'exercices publiés sur PLaTon |
| **Générations sans erreur** | Générations réussies dès le premier essai |
| **Erreurs corrigées (retry)** | Générations avec erreur sandbox corrigée automatiquement |
| **Échecs fatals (sandbox)** | Générations échouées après épuisement des retries |
| **Erreurs internes** | Échecs dus à une erreur système (réseau, LLM, parsing) |
| **Temps de réponse moyen** | Temps entre la requête et la fin de la génération |
| **Tokens en entrée** | Total de tokens envoyés au LLM |
| **Tokens en sortie** | Total de tokens générés par le LLM |
| **Tokens moy. / génération** | Moyenne de tokens par génération |

Le graphique journalier affiche l'évolution de ces métriques sur la période sélectionnée (7, 30, ou 365 jours, ou période personnalisée).

Survolez chaque carte pour afficher une description détaillée de la métrique.

