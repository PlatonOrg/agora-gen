# UC9 : Publier un exercice sur PLaTon

| Champ | Valeur |
|---|---|
| Description | Permet de publier l'exercice final dans un cercle PLaTon avec un statut cible choisi. |
| Paquetage | Finalisation et publication |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Utilisateur connecte, exercice disponible dans le workspace, cercle de destination avec droit d'ecriture disponible. |
| Postconditions | L'exercice est cree sur PLaTon et une confirmation est affichee. |
| Importance | Haute |
| Frequence | Moyenne |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur le bouton **"Publier l'exercice"** dans le workspace. | Ouvre la boite de dialogue de publication. |
| 2 | Dans la boite de dialogue, selectionne le **cercle de destination** dans la liste deroulante. | Met a jour l'affichage avec le cercle selectionne. |
| 3 | Selectionne le **statut de publication** souhaite dans la liste (ex : Brouillon, Pret, Bugge, Non teste). | Met a jour le statut selectionne dans la boite de dialogue. |
| 4 | Clique sur **"Publier"** pour confirmer. | Prepare les fichiers de l'exercice (contenu PLE, parametres, fichier readme si metadonnees presentes) et les envoie a PLaTon. |
| 5 |  | Affiche un indicateur de chargement pendant la publication. |
| 6 |  | Affiche un message de succes dans une notification (ex : "L'exercice a ete publie avec succes sur PLaTon."). |

## Scenarios d'exception

### E1 - Aucun cercle disponible ou exercice introuvable

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Publier l'exercice"**. | Tente d'ouvrir la boite de dialogue de publication mais ne trouve pas l'etat de l'exercice ou aucun cercle accessible. |
| 2 |  | Affiche un message d'erreur (ex : "Impossible de publier : l'exercice n'est pas disponible. Veuillez reessayer ou contacter le support."). |
| 3 | La boite de dialogue ne s'ouvre pas. L'utilisateur reste sur le workspace. |  |

### E2 - Erreur lors de la publication sur PLaTon

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Publier"** dans la boite de dialogue. | Tente d'envoyer l'exercice a PLaTon mais rencontre une erreur reseau ou une erreur du serveur PLaTon. |
| 2 |  | Masque l'indicateur de chargement. |
| 3 |  | Affiche un message d'erreur dans la boite de dialogue ou en notification (ex : "La publication a echoue. Verifiez votre conexion et reessayez."). |
| 4 | Peut cliquer a nouveau sur **"Publier"** pour retenter la publication. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Construction des fichiers a publier | Integrite | Les fichiers envoyes refletent exactement l'etat courant de l'exercice. |
| Publication distante | Fiabilite | Retour explicite success ou erreur apres tentative de publication. |
