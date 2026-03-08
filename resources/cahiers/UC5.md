# UC5 : Gerer les fichiers joints de session

| Champ | Valeur |
|---|---|
| Description | Permet d'ajouter des fichiers a la conversation, de les reutiliser entre messages et de les supprimer. |
| Paquetage | Assistance par contexte fichier |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Utilisateur connecte, conversation ouverte. |
| Postconditions | Les fichiers sont associes a la session et exploites par l'agent comme contexte supplementaire. |
| Importance | Moyenne a haute |
| Frequence | Frequence variable |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur l'icone **"Joindre un fichier"** (trombone) dans la barre de saisie, ou glisse-depose un fichier directement dans la zone de discussion. | Ouvre l'explorateur de fichiers (si clic) ou detecte le fichier depose. |
| 2 | Selectionne le fichier a ajouter. | Verifie que le type et la taille du fichier sont autorises. |
| 3 |  | Affiche une vignette ou un badge du fichier joint dans la zone de saisie, avec son nom. |
| 4 | Redige son message et clique sur **"Envoyer"**. | Associe le fichier au message envoye, extrait le contenu textuel et affiche le fichier dans la conversation. |
| 5 |  | Conserve le fichier en session : il sera reutilise comme contexte dans les messages suivants (en version resumee). |
| 6 | Pour nettoyer, clique sur le bouton **"Supprimer les fichiers de session"** ou sur la croix d'une vignette individuelle. | Supprime l'association du ou des fichiers et retire leurs vignettes de l'interface. |

## Scenarios alternatifs

### A1 - Reutilisation d'un fichier precedemment joint

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Envoie un nouveau message sans joindre de nouveau fichier. | Detecte que des fichiers sont deja associes a la session. |
| 2 |  | Injecte automatiquement le resume du fichier precedemment joint comme contexte du nouveau message, sans action de l'utilisateur. |
| 3 | Recoit une reponse de l'agent qui tient compte du contenu du fichier. |  |

## Scenarios d'exception

### E1 - Type de fichier non supporte

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Tente de joindre un fichier dont le format n'est pas accepte (ex : fichier executables .exe, .bin). | Detecte que le type du fichier n'est pas dans la liste des formats autorises. |
| 2 |  | Affiche une notification d'erreur en haut de la page ou sous la zone de saisie (ex : "Ce type de fichier n'est pas supporte. Formats acceptes : PDF, TXT, DOCX, etc."). |
| 3 | Lit le message d'erreur et peut choisir un autre fichier dans un format compatible. |  |

### E2 - Limite du nombre de fichiers atteinte

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Tente de joindre un fichier alors que la limite de fichiers par session est deja atteinte. | Detecte que le nombre maximum de fichiers est depasse. |
| 2 |  | Affiche un message d'avertissement (ex : "Nombre maximum de fichiers atteint. Supprimez un fichier existant pour en ajouter un nouveau."). |
| 3 | Clique sur la croix d'un fichier existant pour le supprimer. | Retire le fichier de la session et libere un emplacement. |
| 4 | Peut desormais joindre un nouveau fichier. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Validation upload | Securite | Rejet des types non supportes avec message explicite. |
| Contexte conversationnel | Efficacite | Reutilisation automatique des fichiers de session pour enrichir le contexte. |
| Nettoyage session | Maintenabilite | Suppression possible fichier par fichier ou en masse en une action. |
