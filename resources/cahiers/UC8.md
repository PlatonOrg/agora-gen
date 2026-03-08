# UC8 : Previsualiser un exercice et consulter son PLE

| Champ | Valeur |
|---|---|
| Description | Permet de generer un apercu PLaTon de l'exercice (ou d'un template parametre) et de consulter le code PLE produit. |
| Paquetage | Validation avant publication |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Un exercice ou un template parametre est disponible dans le workspace. |
| Postconditions | L'apercu est ouvert dans un nouvel onglet et/ou le contenu PLE est affiche dans une fenetre. |
| Importance | Haute |
| Frequence | Frequence reguliere |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Dans le workspace, clique sur le bouton **"Voir l'exercice"** (ou **"Voir l'apercu"**). | Genere l'apercu PLaTon de l'exercice courant. |
| 2 |  | Affiche un indicateur de chargement pendant la generation. |
| 3 |  | Ouvre automatiquement l'apercu PLaTon dans un **nouvel onglet** du navigateur. |
| 4 | Consulte l'exercice rendu dans PLaTon depuis le nouvel onglet, puis revient sur AGORA. | L'apercu reste accessible tant que l'onglet est ouvert. |
| 5 | Clique sur le bouton **"Voir le PLE"**. | Genere le code source PLE de l'exercice. |
| 6 |  | Affiche le contenu PLE dans une **fenetre modale** (popup) de lecture. |
| 7 | Consulte le code PLE et ferme la popup en cliquant sur **"Fermer"** ou la croix. | Ferme la fenetre modale. |

## Scenarios alternatifs

### A1 - Reutilisation de l'apercu en cache

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Voir l'exercice"** sans avoir modifie l'exercice depuis le dernier apercu. | Detecte qu'un apercu recemment genere est encore disponible. |
| 2 |  | Reutilise l'URL d'apercu existante au lieu d'en generer une nouvelle. |
| 3 |  | Ouvre l'apercu dans un nouvel onglet instantanement, sans delai de generation. |

## Scenarios d'exception

### E1 - Echec de generation de l'apercu

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Voir l'exercice"**. | Tente de generer l'apercu PLaTon mais rencontre une erreur (ex : erreur de compilation, service PLaTon indisponible). |
| 2 |  | Masque l'indicateur de chargement. |
| 3 |  | Affiche un message d'erreur dans la zone de discussion ou en notification (ex : "La generation de l'apercu a echoue. Verifiez le contenu de l'exercice ou reessayez."). |
| 4 | Lit le message, corrige eventuellement l'exercice et clique a nouveau sur **"Voir l'exercice"**. |  |

### E2 - Echec de generation du contenu PLE

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Voir le PLE"**. | Tente de generer le code PLE mais rencontre une erreur. |
| 2 |  | N'ouvre pas la fenetre modale. |
| 3 |  | Affiche un message d'erreur en notification (ex : "Impossible d'afficher le PLE pour le moment."). |
| 4 | Lit le message et peut reessayer ulterieurement. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Apercu externe | Conformite | L'apercu ouvert dans le nouvel onglet reflete exactement l'etat courant de l'exercice. |
| Consultation PLE | Transparence | L'utilisateur peut auditer le code PLE genere avant publication. |
