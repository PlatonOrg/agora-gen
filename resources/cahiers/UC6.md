# UC6 : Rechercher et appliquer un template

| Champ | Valeur |
|---|---|
| Description | Permet de filtrer les templates disponibles, d'en consulter un apercu, puis d'appliquer un template a l'exercice en cours. |
| Paquetage | Reutilisation de templates |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Workspace initialise (cercles, sujets, niveaux et composants charges). |
| Postconditions | L'exercice courant est remplace par une structure basee sur le template choisi. |
| Importance | Haute |
| Frequence | Frequence reguliere |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur l'onglet **"Templates"** dans le panneau lateral du workspace. | Affiche le panneau de recherche de templates avec les filtres disponibles. |
| 2 | Renseigne les filtres souhaites : cercle, sujets, niveaux, composants et/ou mot-cle dans le champ de texte. | Met a jour les filtres selectionnes visuellement. |
| 3 | Clique sur le bouton **"Rechercher"**. | Affiche la liste des templates correspondant aux filtres dans le panneau. |
| 4 | Parcourt les resultats. Clique sur le bouton **"Apercu"** d'un template. | Ouvre l'apercu du template PLaTon dans un nouvel onglet du navigateur. |
| 5 | Revient sur AGORA et clique sur **"Utiliser ce template"**. | Affiche une boite de dialogue de confirmation (ex : "Appliquer ce template remplacera le contenu actuel de l'exercice. Confirmer ?"). |
| 6 | Clique sur **"Confirmer"** dans la boite de dialogue. | Charge le contenu du template dans l'exercice courant (titre, composants, parametres configurables) et met a jour le panneau d'edition. |

## Scenarios alternatifs

### A1 - Annulation de l'application du template

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Utiliser ce template"**. | Affiche la boite de dialogue de confirmation. |
| 2 | Clique sur **"Annuler"** dans la boite de dialogue. | Ferme la boite de dialogue. |
| 3 | L'exercice courant reste inchange. |  |

## Scenarios d'exception

### E1 - Aucun resultat pour les filtres saisis

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Renseigne des filtres tres restrictifs et clique sur **"Rechercher"**. | Effectue la recherche et ne trouve aucun template correspondant. |
| 2 |  | Affiche un message dans le panneau (ex : "Aucun template ne correspond a vos criteres. Essayez d'elargir vos filtres."). |
| 3 | Modifie ou supprime certains filtres et relance la recherche. |  |

### E2 - Echec de la recherche de templates

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Rechercher"**. | Tente de recuperer les templates disponibles mais rencontre une erreur reseau ou serveur. |
| 2 |  | Affiche un message d'erreur dans le panneau (ex : "Impossible de charger les templates. Veuillez reessayer."). |
| 3 | L'interface reste utilisable, l'utilisateur peut reessayer. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Recherche filtree | Pertinence | Les templates affiches correspondent exactement aux filtres appliques. |
| Application de template | Securite fonctionnelle | Confirmation explicite avant tout remplacement du contenu de l'exercice. |
