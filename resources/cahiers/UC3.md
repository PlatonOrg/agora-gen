# UC3 : Poser une question documentaire (mode Ask)

| Champ | Valeur |
|---|---|
| Description | Permet a l'utilisateur de poser une question sur la documentation PLaTon sans generation d'exercice. |
| Paquetage | Discussion documentaire |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Utilisateur connecte, workspace ouvert, mode "Ask" selectionne. |
| Postconditions | Une reponse textuelle est affichee dans la conversation. |
| Importance | Moyenne |
| Frequence | Frequence variable selon usage |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Dans le workspace, clique sur le selecteur de mode et choisit **"Ask"**. | Met en evidence la zone de discussion en mode Ask. |
| 2 | Saisit sa question dans le champ de texte en bas de la conversation. | Affiche le texte saisi en temps reel dans le champ. |
| 3 | Clique sur le bouton **"Envoyer"** (ou appuie sur Entree). | Affiche le message de l'utilisateur dans la conversation et lance la recherche documentaire. |
| 4 |  | Affiche un indicateur de chargement dans la conversation (animation de saisie). |
| 5 |  | Affiche la reponse progressivement dans la conversation (effet de frappe lettre par lettre). |

## Scenarios alternatifs

### A1 - Relance de question depuis l'historique

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Fait defiler l'historique de la conversation pour retrouver une question anterieure. | Affiche l'historique complet des echanges dans la zone de discussion. |
| 2 | Copie le texte d'une reponse ou d'une question anterieure. | Copie le texte dans le presse-papier. |
| 3 | Colle le texte dans le champ de saisie, l'ajuste et envoie. | Traite la nouvelle question comme une nouvelle soumission. |

## Scenarios d'exception

### E1 - Service documentaire indisponible

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Envoyer"** pour soumettre sa question. | Tente d'interroger le service de documentation PLaTon. |
| 2 |  | Detecte que le service est indisponible ou en erreur. |
| 3 |  | Affiche un message d'erreur dans la zone de conversation (ex : "Le service de documentation est momentanement indisponible. Veuillez reessayer."). |
| 4 | Lit le message d'erreur et peut reessayer en renvoyant sa question. |  |

### E2 - Champ de saisie vide

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur **"Envoyer"** sans avoir saisi de texte. | Detecte que le champ de saisie est vide. |
| 2 |  | Desactive le bouton "Envoyer" ou affiche une indication visuelle invitant a saisir du texte. |
| 3 | Saisit sa question et clique de nouveau sur **"Envoyer"**. |  |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Reponse documentaire | Pertinence | La reponse doit etre contextualisee sur la documentation PLaTon. |
| Retour d'erreur | Lisibilite | Message d'erreur clair et non bloquant affiche en cas de probleme. |
