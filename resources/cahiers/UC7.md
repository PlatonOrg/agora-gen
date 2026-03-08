# UC7 : Editer un exercice (contenu, composants, metadonnees)

| Champ | Valeur |
|---|---|
| Description | Permet d'editer integralement l'exercice (champs pedagogiques, scripts, variables, composants PLaTon, topics et niveaux). |
| Paquetage | Edition et personnalisation |
| Acteurs | Enseignant, Administrateur |
| Preconditions | Un exercice est present dans le workspace (vide, genere ou base sur un template). |
| Postconditions | Le contenu de l'exercice est mis a jour dans l'etat courant et pret pour apercu ou publication. |
| Importance | Haute |
| Frequence | Tres frequente |

## Scenario nominal

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Dans le panneau d'edition, clique sur un champ (ex : **"Titre"**, **"Enonce"**, **"Solution"**) et modifie le contenu directement. | Met a jour l'etat de l'exercice en temps reel a chaque frappe. |
| 2 | Pour les scripts ou variables avancees, clique sur les onglets **"Scripts"** ou **"Variables"** et edite le contenu dans l'editeur de code integre. | Rafrachit l'etat de l'exercice avec les nouvelles valeurs. |
| 3 | Pour ajouter un composant, le fait glisser depuis le panneau **"Composants"** et le depose dans la zone de composants de l'exercice. | Ajoute le composant a l'exercice et met a jour les variables sandbox correspondantes. |
| 4 | Pour supprimer un composant, clique sur l'icone de suppression (corbeille) du composant dans la liste. | Retire le composant et nettoie les variables sandbox associees. |
| 5 | Clique sur l'onglet **"Metadonnees"**. | Charge et affiche les tags PLaTon disponibles (topics, niveaux) avec des suggestions automatiques. |
| 6 | Coche ou saisit les topics et niveaux souhaites, puis valide. | Enregistre les metadonnees dans l'etat de l'exercice. |

## Scenarios alternatifs

### A1 - Edition d'un exercice base sur un template

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Un template est actif sur l'exercice. L'utilisateur clique sur l'onglet **"Parametres"**. | Affiche les parametres configurables du template (variables exposees par le template). |
| 2 | Modifie les valeurs des parametres du template dans les champs affiches. | Met a jour les valeurs configurables en temps reel. |
| 3 | Tente de modifier un script marque en lecture controlee. | Affiche un avertissement visuel (champ grise ou cadenas) indiquant que ce champ est gere par le template. |
| 4 | Prend connaissance de l'avertissement et se concentre sur les parametres modifiables. |  |

### A2 - Reinitialisation de l'exercice

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Clique sur le bouton **"Reinitialiser l'exercice"**. | Affiche une boite de dialogue de confirmation (ex : "Cette action supprimera tout le contenu de l'exercice. Continuer ?"). |
| 2 | Clique sur **"Confirmer"**. | Vide tous les champs de l'exercice et remet l'etat a zero. |
| 3 | Le panneau d'edition affiche un exercice vide, pret pour une nouvelle saisie ou generation. |  |

## Scenarios d'exception

### E1 - Saisie JSON invalide dans une propriete de composant

| Etape | Acteur | Systeme |
|---|---|---|
| 1 | Saisit une valeur JSON malformee dans le champ d'une propriete de composant. | Detecte l'erreur de format JSON en temps reel. |
| 2 |  | Affiche un indicateur d'erreur visuel sur le champ concerne (bordure rouge, icone d'alerte, message "Format JSON invalide"). |
| 3 | Lit l'indication d'erreur et corrige la valeur dans le champ. | Retire l'indicateur d'erreur des que la valeur est valide. |

## FQM (Fonction, Qualite, Mesure)

| Macro-fonctionnalite | Qualite attendue | Mesure / Critere |
|---|---|---|
| Edition temps reel | Ergonomie | Les changements sont reflechis immediatement dans l'etat de l'exercice. |
| Configuration composants | Coherence | Synchronisation continue entre instances de composants et variables sandbox. |
| Edition metadonnees | Controle | Topics et niveaux modifiables avant publication. |
