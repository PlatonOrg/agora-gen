# UC1 : S'authentifier sur PLaTon

| Champ | Valeur |
|---|---|
| Description | Permet a un enseignant ou un administrateur d'ouvrir une session AGORA via l'authentification PLaTon. |
| Paquetage | Gestion d'acces |
| Acteurs | Enseignant, Administrateur, Plateforme PLaTon |
| Preconditions | L'utilisateur possede un compte PLaTon actif. AGORA est accessible. |
| Postconditions | L'utilisateur est connecte et accede au workspace AGORA. |
| Importance | Haute |
| Frequence | Haute |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Ouvre AGORA dans son navigateur. | Affiche la page de connexion avec le bouton **"S'authentifier sur PLaTon"**. |
| 2 | Clique sur le bouton **"S'authentifier sur PLaTon"**. | Prepare la connexion securisee et redirige l'utilisateur vers la page d'authentification PLaTon. |
| 3 | Saisit ses identifiants PLaTon (login + mot de passe) et valide. | Recoit la confirmation de PLaTon et redirige l'utilisateur vers AGORA. |
| 4 |  | Verifie la reponse de PLaTon, cree la session utilisateur et recupere le profil (nom, role). |
| 5 |  | Redirige automatiquement l'utilisateur vers le **workspace**. |

## Scenarios alternatifs

### A1 - Session deja valide

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Ouvre AGORA dans son navigateur (ou actualise la page). | Detecte automatiquement qu'une session active est deja presente. |
| 2 |  | Redirige directement l'utilisateur vers le workspace sans afficher la page de connexion. |
| 3 | Arrive directement sur le workspace sans avoir a se reconnecter. |  |

## Scenarios d'exception

### E1 - Echec d'authentification PLaTon

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Saisit des identifiants incorrects sur PLaTon ou annule la connexion. | Recoit une reponse d'echec de PLaTon. |
| 2 |  | Annule la tentative de connexion en cours. |
| 3 |  | Affiche un message d'erreur explicite sur la page de connexion (ex : "Echec de l'authentification PLaTon. Veuillez reessayer."). |
| 4 | Lit le message d'erreur et peut cliquer a nouveau sur **"S'authentifier sur PLaTon"** pour reessayer. |  |

### E2 - Session expiree en cours d'utilisation

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Effectue une action dans AGORA (envoi de message, modification d'exercice, etc.). | Detecte que la session utilisateur n'est plus valide (expiree). |
| 2 |  | Efface automatiquement l'etat de connexion local. |
| 3 |  | Redirige l'utilisateur vers la page de connexion avec un message d'information (ex : "Votre session a expire. Veuillez vous reconnecter."). |
| 4 | Arrive sur la page de connexion et clique sur **"S'authentifier sur PLaTon"** pour reprendre sa session. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Initialisation de la connexion | Fiabilite | L'utilisateur est redirige vers PLaTon en 100% des cas apres clic sur le bouton. |
| Protection des acces | Securite | Aucune page protegee n'est accessible sans session valide. |
| Retour utilisateur | Ergonomie | Message d'erreur clair et actionnable affiche en cas d'echec. |
