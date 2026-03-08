# UC4 : Generer ou modifier un exercice avec l'agent IA (mode Agent)

| Champ | Valeur |
|---|---|
| Description | Conversation multi-tour avec l'agent pour generer ou modifier un exercice, avec suivi de progression en temps reel, apercu et correction automatique. |
| Paquetage | Generation d'exercices |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Utilisateur connecte, mode "Agent" actif dans le workspace. |
| Postconditions | L'exercice est mis a jour, un apercu est genere si la generation est reussie, et la conversation conserve la trace des etapes. |
| Importance | Haute |
| Frequence | Tres frequente |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur le selecteur de mode et choisit **"Agent"**. | Active le mode agent dans la zone de discussion. |
| 2 | Saisit sa demande de generation ou de modification dans le champ de texte (ex : "Cree un exercice de mathematiques sur les fractions pour le college"). | Affiche le texte saisi dans le champ. |
| 3 | Clique sur **"Envoyer"**. | Affiche le message dans la conversation et ouvre la timeline de progression. |
| 4 |  | Affiche les etapes de traitement en temps reel dans la timeline : recuperation du contexte, generation du contenu, compilation et apercu. |
| 5 |  | Met a jour le panneau d'edition avec le contenu de l'exercice genere (titre, enonce, solution, composants, etc.). |
| 6 |  | Affiche un bouton **"Voir l'apercu"** et ouvre automatiquement l'apercu PLaTon dans un nouvel onglet. |

## Scenarios alternatifs

### A1 - Arret manuel de la generation

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Pendant la generation, observe la timeline en cours. | Affiche les etapes en cours avec un bouton **"Arreter"** visible. |
| 2 | Clique sur le bouton **"Arreter"**. | Recoit l'ordre d'arret et annule la generation en cours. |
| 3 |  | Marque la timeline avec un statut d'arret controle (ex : icone d'arret sur la derniere etape). |
| 4 |  | Affiche un message dans la conversation indiquant que la generation a ete interrompue par l'utilisateur. |
| 5 | Peut saisir une nouvelle demande ou modifier sa requete et renvoyer. |  |

### A2 - Modification ciblee avec badges

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur les badges de champs disponibles sous le champ de saisie (ex : badge **"Enonce"**, badge **"Solution"**, badge composant). | Met en evidence les badges selectionnes et les ajoute comme contexte de la requete. |
| 2 | Saisit une instruction de modification dans le champ de texte (ex : "Rends l'enonce plus simple"). | Affiche le texte et les badges selectionnes dans le champ. |
| 3 | Clique sur **"Envoyer"**. | Lance la generation en limitant les modifications aux champs/composants cibles par les badges. |
| 4 |  | Met a jour uniquement les champs concernes dans le panneau d'edition, sans toucher au reste de l'exercice. |

## Scenarios d'exception

### E1 - Erreur de compilation avec tentatives de correction automatique

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | L'utilisateur a envoye une demande. La generation du contenu est terminee. | Tente de generer l'apercu PLaTon et detecte une erreur de compilation. |
| 2 |  | Affiche dans la timeline une etape "Correction en cours" avec un numero de tentative (ex : "Correction 1/3"). |
| 3 |  | Relance automatiquement une tentative de correction et d'apercu. |
| 4 | Observe la timeline qui se met a jour a chaque tentative. |  |
| 5 |  | Si la correction reussit : affiche l'apercu et met a jour l'exercice normalement (suite du scenario nominal). |

### E2 - Echec final apres epuisement des tentatives

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Observe la timeline qui indique "Correction 3/3" ou la limite est atteinte. | Detecte que toutes les tentatives de correction ont echoue. |
| 2 |  | Marque la timeline en erreur finale avec une icone rouge sur la derniere etape. |
| 3 |  | Affiche un message d'erreur dans la conversation expliquant l'echec (ex : "La generation a echoue apres plusieurs tentatives. Veuillez reformuler votre demande ou contacter le support."). |
| 4 | Lit le message, peut reformuler sa demande et cliquer sur **"Envoyer"** a nouveau. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Suivi de progression | Transparence | L'utilisateur voit les etapes de generation en quasi temps reel dans la timeline. |
| Robustesse de generation | Fiabilite | Gestion explicite des tentatives de correction et des erreurs terminales. |
| Controle utilisateur | Maitrise | L'utilisateur peut arreter une generation en cours a tout moment. |
