# Recette de Recette — Agora AI Agent

> **Version** : 1.0 — Mars 2026  
> **Environnement cible** : Recette (staging) connecté à PLaTon Université Gustave Eiffel  
> **Prérequis** : Deux comptes PLaTon disponibles — un compte **enseignant** (ex. `prof_test`) et un compte **administrateur** (ex. `admin_test`). Un fichier `data.csv` de 10 lignes de Q&R, un fichier `image.png` binaire, et un fichier `doc.txt` de contenu pédagogique préparés localement.

---

## Conventions

| Symbole | Signification |
|---------|--------------|
| ✅ | Résultat attendu (à cocher si OK) |
| 🔢 | Jeu de données à saisir |
| ⚠️ | Point d'attention |
| 👤 | Compte utilisateur requis |

---

## 1. Authentification

### 1.1 Connexion compte enseignant
> 👤 Compte : `prof_test` (rôle enseignant, pas administrateur)

| # | Action | Résultat attendu |
|---|--------|-----------------|
| 1.1.1 | Ouvrir l'application et cliquer sur « Se connecter avec PLaTon » | La page de connexion PLaTon s'affiche |
| 1.1.2 | Se connecter avec le compte `prof_test` | Redirection vers l'espace de travail (workspace) |
| 1.1.3 | Cliquer sur l'avatar en haut à droite | Le menu utilisateur s'ouvre et affiche le nom/prénom et le username |
| 1.1.4 | Vérifier la présence du lien « Administration » dans le menu | Le lien est présent |
| 1.1.5 | Cliquer sur « Administration » et vérifier la page des journaux | On accède aux journaux (conversations) mais la page d'administration (statistiques avancées) n'est pas accessible depuis le profil — l'onglet « Statistiques » du tableau de bord admin ne s'affiche pas |

### 1.2 Connexion compte administrateur
> 👤 Compte : `admin_test` (rôle administrateur)

| # | Action | Résultat attendu |
|---|--------|-----------------|
| 1.2.1 | Se connecter avec le compte `admin_test` | Redirection vers l'espace de travail |
| 1.2.2 | Cliquer sur l'avatar en haut à droite | Le menu utilisateur affiche « Administration » et « Statistiques » |
| 1.2.3 | Cliquer sur « Administration » | La page des journaux s'ouvre avec les onglets Conversations, Statistiques, Configuration |
| 1.2.4 | Naviguer vers l'onglet « Statistiques » | Le tableau de bord des statistiques s'affiche correctement |

### 1.3 Déconnexion et persistance de session
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 1.3.1 | Cliquer sur « Se déconnecter » dans le menu utilisateur | Redirection vers la page de connexion |
| 1.3.2 | Fermer le navigateur complètement et le rouvrir, naviguer vers l'application | La page de connexion s'affiche — l'utilisateur n'est pas reconnecté automatiquement |
| 1.3.3 | Se reconnecter avec `prof_test` | Connexion réussie, retour à l'espace de travail |

### 1.4 Accès non autorisé
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 1.4.1 | Sans être connecté, accéder directement à `/workspace` | Redirection vers la page de connexion |
| 1.4.2 | Sans être connecté, accéder directement à `/admin` | Redirection vers la page de connexion |

---

## 2. Espace de travail — Interface générale

### 2.1 Disposition et panneaux
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 2.1.1 | Ouvrir l'espace de travail | Trois zones visibles : panneau gauche (discussion), panneau central (exercice), panneau droit (modèles/composants) |
| 2.1.2 | Cliquer sur le bouton de bascule du panneau gauche (icône en haut à gauche) | Le panneau gauche (discussion) se masque / se réaffiche |
| 2.1.3 | Ouvrir les deux panneaux latéraux simultanément | Les boutons de la barre d'en-tête se réduisent à leurs icônes (les labels texte disparaissent) |
| 2.1.4 | Redimensionner la fenêtre du navigateur à moins de 900 px de large | Les labels texte des boutons disparaissent, seules les icônes restent |
| 2.1.5 | Cliquer sur le bouton « Guide » dans l'en-tête | Le guide de démarrage (tour) se lance avec des infobulles de navigation |
| 2.1.6 | Naviguer jusqu'à la fin du guide et le fermer | Le guide se ferme sans modifier l'état de l'exercice |

### 2.2 Réinitialisation de l'exercice
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 2.2.1 | 🔢 Saisir manuellement dans les champs : Titre = `Mon exercice test`, Énoncé = `Calculez 2+2`, Solution = `4` | Les champs sont remplis |
| 2.2.2 | Cliquer sur « Réinitialiser » dans la barre d'en-tête | Une boîte de dialogue de confirmation s'affiche avec le message d'avertissement |
| 2.2.3 | Cliquer sur « Annuler » dans la boîte de dialogue | Aucun champ n'est modifié, l'exercice est intact |
| 2.2.4 | Cliquer de nouveau sur « Réinitialiser » puis confirmer en cliquant « Réinitialiser » | Tous les champs de l'exercice sont vidés ET l'historique de conversation est effacé |

---

## 3. Discussion — Mode « Discuter » (RAG documentaire)

### 3.1 Question simple
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 3.1.1 | Sélectionner le mode « Discuter » dans le sélecteur de mode | Le mode est basculé sur « Discuter » |
| 3.1.2 | 🔢 Envoyer : `À quoi sert le composant jsx ?` | L'IA répond avec une explication textuelle du composant `wc-jsx`, sans générer d'exercice |
| 3.1.3 | 🔢 Envoyer : `Quelles sont les propriétés du composant wc-input-box ?` | L'IA liste les propriétés du composant `wc-input-box` avec leurs types et descriptions |
| 3.1.4 | 🔢 Envoyer : `Comment fonctionne le grader dans PLaTon ?` | L'IA explique le cycle de vie du grader (variables `grade` et `feedback`) |

### 3.2 Historique de conversation en mode discussion
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 3.2.1 | Envoyer plusieurs questions en mode Discuter à la suite | Chaque échange s'affiche dans le fil de discussion de manière cohérente |
| 3.2.2 | Cliquer sur « Effacer la conversation » dans le menu du panneau | Une boîte de dialogue de confirmation s'affiche |
| 3.2.3 | Confirmer l'effacement | L'historique de conversation est vidé, le contenu de l'exercice n'est pas affecté |

---

## 4. Génération d'exercices — Mode « Générer »

### 4.1 Génération avec sélection automatique de template (RAG template)
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.1.1 | Sélectionner le mode « Générer » et s'assurer que l'option « Exercice entièrement personnalisé » est **désactivée** | Le mode de génération est standard (avec RAG template) |
| 4.1.2 | 🔢 Envoyer : `je veux un exercice de math pour les élèves Licence 1 sur le positionnement d'un point dans un composant jsx` | Un exercice est généré en utilisant le template **« Positionnement point (modèle) (JSX) »**. L'onglet Paramètres est visible dans l'exercice |
| 4.1.3 | Vérifier que le badge « Template » est affiché dans la barre d'en-tête | Le badge indique le nom du template utilisé |
| 4.1.4 | Vérifier l'onglet « Paramètres » dans le panneau exercice | Les paramètres du template sont visibles et modifiables |

### 4.2 Génération d'exercice entièrement personnalisé (sans template)
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.2.1 | **Activer** l'option « Exercice entièrement personnalisé » avant d'envoyer la première demande | L'indicateur visuel confirme le mode personnalisé |
| 4.2.2 | 🔢 Envoyer : `je veux un exercice de math pour les élèves Licence 1 sur le positionnement d'un point dans un composant jsx` | Un exercice est généré **sans template**, à partir de zéro. Les champs Builder, Grader, Énoncé, Forme, Solution sont remplis. Aucun badge « Template » n'apparaît |
| 4.2.3 | Vérifier que le mode est verrouillé après la première génération | L'option « Exercice entièrement personnalisé » n'est plus modifiable (verrouillée) |

### 4.3 Génération avec composant imposé par l'utilisateur
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.3.1 | Activer « Exercice entièrement personnalisé » | Mode activé |
| 4.3.2 | Dans le panneau composants, glisser-déposer `wc-radio-group` vers l'onglet composants de l'exercice OU sélectionner le composant `wc-radio-group` depuis le panneau | Le composant `wc-radio-group` est ajouté aux composants sélectionnés (badge visible dans la zone de saisie) |
| 4.3.3 | 🔢 Envoyer : `génère moi un exercice de questions générales sur le thème de la 2ème guerre mondiale` | L'exercice généré utilise **obligatoirement** le composant `wc-radio-group` |

### 4.4 Génération avec fichier joint (données)
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.4.1 | Cliquer sur l'icône trombone dans la zone de saisie et sélectionner `data.csv` (10 lignes de Q&R) | Le fichier `data.csv` est joint (un indicateur s'affiche dans la zone de saisie) et une animation de chargement est visible pendant le traitement |
| 4.4.2 | 🔢 Envoyer : `fais moi un exercice de questions-réponses (type QCM) avec les questions du fichier que j'ai joint` | L'exercice généré intègre les données du fichier CSV joint. Les questions et réponses correspondent aux données du fichier |
| 4.4.3 | Vérifier que dans les messages suivants, seul le **résumé** du fichier est attaché (pas le contenu intégral) | Les appels LLM ultérieurs n'envoient que le résumé du fichier, pas le texte complet |

### 4.5 Limite du nombre de fichiers joints
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.5.1 | Tenter de joindre 10 fichiers différents à la conversation (dépasse la limite de 5) | Seuls les 5 premiers fichiers (ou la limite configurée) sont acceptés. Un message d'erreur s'affiche pour les fichiers en excès |
| 4.5.2 | Joindre 5 fichiers, les envoyer dans une génération, puis tenter d'en joindre 5 autres | Les 5 nouveaux fichiers sont correctement joints sans problème |

### 4.6 Annulation de l'attachement de fichier et re-attachement
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.6.1 | Joindre un fichier `doc.txt` puis le supprimer (cliquer sur la croix de l'indicateur de fichier) | Le fichier est retiré de la zone de saisie |
| 4.6.2 | Répéter l'opération (joindre + supprimer) 5 fois de suite | À chaque fois le fichier est bien retiré. Au 5e retrait, il est toujours possible d'attacher de nouveau un fichier — la limite n'est pas atteinte (les annulations ne comptent pas dans la limite) |
| 4.6.3 | Joindre `doc.txt`, l'annuler, puis joindre un autre fichier `data.csv` et envoyer une génération | Seul `data.csv` est pris en compte dans la génération |

### 4.7 Gestion des erreurs de fichiers
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.7.1 | Tenter de joindre un fichier `image.png` (fichier binaire) | Un message d'erreur spécifique s'affiche : **« Le type du fichier `image.png` n'est pas supporté. Seuls les documents textuels sont acceptés (pas de fichiers binaires). »** |
| 4.7.2 | Tenter de joindre un fichier texte très volumineux (> 3 000 tokens) | Un message d'erreur spécifique s'affiche : **« Le fichier `[nom]` dépasse la limite de taille autorisée. Veuillez utiliser un fichier plus petit. »** |
| 4.7.3 | Vérifier qu'une animation s'affiche sur l'icône de fichier pendant le traitement | L'animation de traitement est visible pendant l'upload et disparaît une fois le fichier prêt ou en erreur |

### 4.8 Modification ciblée d'un champ via glisser-déposer
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.8.1 | Générer un premier exercice quelconque pour avoir un état initial | L'exercice est généré |
| 4.8.2 | Glisser l'icône du champ « Énoncé » depuis le panneau exercice vers la zone de discussion | Le badge du champ « Énoncé » apparaît dans la zone de saisie de la discussion |
| 4.8.3 | 🔢 Envoyer : `génère moi un énoncé long avec 1 exemple détaillé du calcul du PGCD de 2 nombres` | L'IA génère **uniquement** la valeur du champ « Énoncé ». Seul ce champ est modifié dans l'exercice |
| 4.8.4 | Glisser le champ « Énoncé » dans la discussion et 🔢 envoyer : `génère moi une solution détaillée avec 2 exemples explicatifs` | L'IA tente de modifier la solution (champ non joint). Seul le champ « Énoncé » est potentiellement modifié, le champ « Solution » ne doit pas être impacté ⚠️ |

### 4.9 Modification itérative (conversation multi-tours)
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.9.1 | Après une première génération, 🔢 envoyer : `ajoute une deuxième question sur le même thème` | L'exercice est modifié en tenant compte de l'historique — la modification est cohérente avec l'exercice existant |
| 4.9.2 | 🔢 Envoyer : `rends l'exercice plus difficile` | L'exercice est durci en s'appuyant sur le contexte des échanges précédents |

### 4.10 Bouton « Stop » pendant une génération
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 4.10.1 | Lancer une génération et immédiatement cliquer sur le bouton « Stop » | La génération est interrompue, un message indique l'annulation. L'état de l'exercice avant la génération est préservé |

---

## 5. Panneau exercice — Édition manuelle et onglets

### 5.1 Onglets de l'exercice
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 5.1.1 | Cliquer sur l'onglet « Contenu » | Les champs Titre, Énoncé, Forme, Solution s'affichent |
| 5.1.2 | Cliquer sur l'onglet « Composants » | La liste des composants sélectionnés pour l'exercice s'affiche avec possibilité d'ajout/suppression |
| 5.1.3 | Cliquer sur l'onglet « Aide » | Les champs Indices et Théories s'affichent |
| 5.1.4 | Cliquer sur l'onglet « Scripts » | Les éditeurs Monaco pour Builder et Grader s'affichent avec coloration syntaxique |
| 5.1.5 | Cliquer sur l'onglet « Métadonnées » | Les champs Niveaux, Sujets, Readme, Objectifs pédagogiques s'affichent |

### 5.2 Édition manuelle des champs
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 5.2.1 | 🔢 Saisir dans le champ Titre : `Calcul du PGCD` | Le champ se met à jour en temps réel |
| 5.2.2 | 🔢 Saisir dans le champ Énoncé : `Calculez le PGCD de 12 et 18.` | Le champ se met à jour |
| 5.2.3 | 🔢 Dans l'onglet Métadonnées, ajouter les niveaux `Licence 1` et `MathSup1` | Les badges de niveaux s'affichent |
| 5.2.4 | 🔢 Ajouter les sujets `Aléatoire`, `Dénombrement` | Les badges de sujets s'affichent |
| 5.2.5 | 🔢 Saisir dans le champ Readme : `Cet exercice porte sur le PGCD.` | Le champ readme est mis à jour |

### 5.3 Composants — Glisser-déposer depuis le panneau
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 5.3.1 | Ouvrir le panneau des composants (onglet droit) et localiser `wc-input-box` | Le composant est visible avec sa description |
| 5.3.2 | Glisser `wc-input-box` depuis le panneau vers l'onglet « Composants » de l'exercice | Le composant est ajouté à la liste des composants de l'exercice |
| 5.3.3 | 🔢 Dans l'onglet « Forme », saisir manuellement `{{input_box}}` | La variable du composant est insérée dans le champ forme |
| 5.3.4 | Cliquer sur « Prévisualiser » | La prévisualisation s'ouvre sur PLaTon avec le composant `input_box` visible dans le rendu |

### 5.4 Bouton d'info des champs
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 5.4.1 | Cliquer sur le bouton ℹ️ à côté du champ « Titre » | Une infobulle ou un panneau explicatif s'affiche avec la description du champ |
| 5.4.2 | Cliquer en dehors de l'infobulle | L'infobulle se ferme |

### 5.5 Lien vers la documentation des composants
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 5.5.1 | Dans le panneau composants, cliquer sur le bouton de redirection du composant `wc-input-box` | L'utilisateur est redirigé vers la documentation PLaTon du composant dans un nouvel onglet |

---

## 6. Prévisualisation

### 6.1 Prévisualisation d'un exercice valide
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 6.1.1 | Avec un exercice valide généré, cliquer sur « Prévisualiser » dans la barre d'en-tête | Le bouton affiche un indicateur de chargement pendant la requête |
| 6.1.2 | Attendre la fin de la prévisualisation | L'utilisateur est redirigé vers la prévisualisation de l'exercice sur PLaTon dans un nouvel onglet |

### 6.2 Prévisualisation d'un exercice avec erreur de syntaxe
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 6.2.1 | 🔢 Insérer manuellement une erreur dans le builder : ajouter la ligne `== syntaxe_invalide ==` en plein milieu du code | Le champ builder contient une erreur PLE |
| 6.2.2 | Cliquer sur « Prévisualiser » | Un message d'erreur s'affiche dans la discussion indiquant que la prévisualisation a échoué, avec le détail de l'erreur technique |

### 6.3 Bouton « Code PLE »
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 6.3.1 | Cliquer sur « Code PLE » dans la barre d'en-tête | Un panneau ou une popup s'affiche avec le code PLE généré à partir des champs de l'exercice |
| 6.3.2 | Vérifier que le code PLE contient les champs saisis | Le code PLE reflète bien le contenu de l'exercice (titre, énoncé, builder, grader, composants, etc.) |

---

## 7. Publication

### 7.1 Ouverture du dialogue de publication
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 7.1.1 | Cliquer sur le bouton « Publier » dans la barre d'en-tête | Un indicateur de chargement s'affiche sur le bouton et le dialogue de publication s'ouvre |
| 7.1.2 | Vérifier que le bouton « Publier » est désactivé pendant le chargement (liste des cercles) | Le bouton est bloqué pour éviter les doubles clics |
| 7.1.3 | Dérouler la liste des cercles dans le dialogue | L'enseignant voit la liste des cercles auxquels il a accès |

### 7.2 Publication en brouillon sur le cercle personnel
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 7.2.1 | 🔢 Remplir : Titre = `PGCD de deux entiers`, Énoncé = `Calculez le PGCD de 12 et 18.`, Readme = `Exercice sur l'algorithme d'Euclide.`, Niveaux = `Licence 1` + `MathSup1`, Sujets = `Aléatoire` + `Dénombrement` | Tous les champs sont remplis dans le dialogue |
| 7.2.2 | Sélectionner le cercle personnel de l'enseignant et le statut « Brouillon » | Sélection effectuée |
| 7.2.3 | Cliquer sur « Publier » | L'exercice est publié. Un message de succès s'affiche |
| 7.2.4 | Aller sur PLaTon et vérifier le cercle personnel | L'exercice apparaît avec le statut **Brouillon**. Le fichier `main.ple` contient le code PLE. Le fichier `readme.md` contient le readme. Le fichier `tags.md` contient les tags (niveaux et sujets). L'exercice est taggé avec le sujet **Aléatoire** et le niveau **Licence 1** |

### 7.3 Publication avec le statut « Prêt à l'emploi »
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 7.3.1 | Sélectionner le statut « Prêt à l'emploi » et publier sur le cercle personnel | L'exercice est publié avec le statut **Prêt à l'emploi** sur PLaTon |

### 7.4 Compteur de statistiques après publication
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 7.4.1 | 👤 Se connecter en tant qu'`admin_test`, aller dans Statistiques et noter la valeur actuelle de « Exercices publiés » | Valeur notée (ex. : 3) |
| 7.4.2 | Revenir à l'espace de travail et publier un exercice | Publication réussie |
| 7.4.3 | Retourner dans Statistiques | Le compteur « Exercices publiés » a augmenté de 1 (ex. : 4) |

---

## 8. Panneau des modèles (templates)

### 8.1 Recherche par mot-clé
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 8.1.1 | Ouvrir le panneau des modèles (onglet droit) | La liste de tous les templates disponibles s'affiche |
| 8.1.2 | 🔢 Saisir `python` dans le champ de recherche | La liste filtrée affiche uniquement les templates dont le titre ou la description contiennent « python » |
| 8.1.3 | 🔢 Effacer la recherche et saisir `PGCD` | Les templates liés au PGCD apparaissent dans les résultats |
| 8.1.4 | 🔢 Saisir un mot-clé sans correspondance, ex. `xyzabc` | La liste est vide et un message « Aucun résultat » s'affiche |

### 8.2 Filtrage par composant
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 8.2.1 | Ouvrir les filtres et sélectionner le composant `jsx` (wc-jsx) | La liste affiche uniquement les templates utilisant le composant `wc-jsx` |
| 8.2.2 | Vérifier les résultats | Tous les templates affichés contiennent le composant `wc-jsx` |

### 8.3 Filtrage par niveau
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 8.3.1 | Dans les filtres, sélectionner le niveau `Licence 1` | La liste affiche uniquement les templates tagués avec le niveau `Licence 1` |

### 8.4 Filtrage par sujet
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 8.4.1 | Dans les filtres, sélectionner le sujet `Aléatoire` | La liste affiche les templates tagués avec le sujet `Aléatoire` |

### 8.5 Filtrage par cercle
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 8.5.1 | Dans les filtres, sélectionner le cercle `Informatique` | La liste affiche uniquement les templates appartenant au cercle `Informatique` |

### 8.6 Application d'un template
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 8.6.1 | Cliquer sur un template dans la liste pour l'expand | Les détails et paramètres du template s'affichent |
| 8.6.2 | Cliquer sur « Utiliser ce modèle » | Une boîte de dialogue de confirmation s'affiche (« Le contenu actuel sera remplacé ») |
| 8.6.3 | Confirmer | L'exercice est configuré avec le template sélectionné. L'onglet « Paramètres » est visible dans le panneau exercice |
| 8.6.4 | Annuler la boîte de confirmation | L'exercice n'est pas modifié |

---

## 9. Administration — Journaux (Conversations)

### 9.1 Accès et liste des conversations
> 👤 Se connecter en tant qu'`admin_test`

| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.1.1 | Naviguer vers Administration → onglet « Conversations » | La liste des conversations enregistrées s'affiche avec : ID tronqué, nom d'utilisateur, date de création, date de dernière activité, nombre de générations |
| 9.1.2 | Vérifier que les conversations générées lors des tests précédents apparaissent | Les conversations de `prof_test` et `admin_test` sont visibles |

### 9.2 Recherche et filtres
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.2.1 | 🔢 Saisir `prof_test` dans la barre de recherche | Seules les conversations de l'utilisateur `prof_test` s'affichent |
| 9.2.2 | Effacer la recherche et saisir les premières lettres d'un ID de conversation | La conversation correspondante est filtrée |
| 9.2.3 | 🔢 Saisir une date « Du » correspondant à aujourd'hui dans le filtre de dates | Seules les conversations créées aujourd'hui s'affichent |
| 9.2.4 | 🔢 Saisir une date « Du » et « Au » correspondant à une période sans conversation | La liste est vide et le message « Aucune conversation ne correspond aux filtres » s'affiche **sous** la barre de recherche et les filtres (pas au milieu de la page) |
| 9.2.5 | Cliquer sur « Effacer » dans le filtre de dates | Les filtres de dates sont réinitialisés, toutes les conversations réapparaissent |

### 9.3 Tri
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.3.1 | Cliquer sur « Date de création » dans la barre de tri | Les conversations sont triées par date de création (ascendant/descendant selon le clic) |
| 9.3.2 | Cliquer sur « Dernière activité » | Tri par date de dernière activité |
| 9.3.3 | Cliquer sur « Nombre de requêtes » | Tri par nombre de générations dans la conversation |

### 9.4 Détail d'une conversation
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.4.1 | Cliquer sur une conversation dans la liste | L'utilisateur est redirigé vers la **page de détail** de la conversation (pas un accordéon en place) |
| 9.4.2 | Vérifier l'affichage : date de création, utilisateur, liste des générations | Toutes les informations sont visibles |
| 9.4.3 | Vérifier que si une conversation a 0 discussion, le badge « discussion » n'apparaît pas | Le badge est absent si le compteur est 0 |
| 9.4.4 | Cliquer sur une génération individuelle dans la liste | La page de détail de la génération s'ouvre |
| 9.4.5 | Cliquer sur « Retour » | Retour à la liste des générations de la conversation |
| 9.4.6 | Cliquer sur « Retour » depuis la conversation | Retour à la liste des conversations |

### 9.5 Détail d'une génération d'exercice
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.5.1 | Ouvrir le détail d'une génération d'exercice (exercice personnalisé généré) | La page affiche dans l'ordre : **Entrées utilisateur** (message, historique, composants, fichiers avec résumé, état de l'exercice), **Étape RAG** (résultats et scores, décision template/pur), **Étape de sélection de composants** (prompt système, composants choisis et raisonnement), **Génération LLM** (prompt système, sortie LLM, tokens consommés) |
| 9.5.2 | Vérifier la section historique de messages | L'historique s'affiche sous forme de liste lisible (message + composants sélectionnés si applicable) — **pas** en JSON brut |
| 9.5.3 | Vérifier la section consommation de tokens | Les tokens d'entrée, de sortie et le total sont affichés |

### 9.6 Suppression de conversations
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.6.1 | Cliquer sur le bouton poubelle d'une conversation dans la liste | Un bandeau de confirmation s'affiche inline (« Supprimer ? Oui / Non ») |
| 9.6.2 | Cliquer sur « Non » | La conversation n'est pas supprimée |
| 9.6.3 | Cliquer de nouveau sur la poubelle puis sur « Oui » | La conversation est supprimée de la liste |
| 9.6.4 | Vérifier que les statistiques de tokens et de temps de réponse sont mises à jour après suppression | Si toutes les conversations sont supprimées, les tokens et le temps de réponse moyen reviennent à 0 / N/A |
| 9.6.5 | Tester la suppression d'une **conversation orpheline** (sans utilisateur associé) | La conversation orpheline peut être supprimée depuis la liste |

### 9.7 Pagination
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 9.7.1 | S'il y a plus de 15 conversations, vérifier la pagination | Les contrôles de pagination s'affichent. Cliquer sur « Page suivante » change la page |
| 9.7.2 | Naviguer vers la dernière page | La dernière page s'affiche correctement sans doublons |

---

## 10. Administration — Statistiques

### 10.1 Affichage des statistiques
> 👤 Compte `admin_test`

| # | Action | Résultat attendu |
|---|--------|-----------------|
| 10.1.1 | Naviguer vers Administration → onglet « Statistiques » | Les cartes de synthèse s'affichent : Conversations, Exercices publiés, Générations sans erreur, Erreurs corrigées (retry), Échecs fatals (sandbox), Erreurs internes, Temps de réponse moyen, Tokens d'entrée totaux, Tokens de sortie totaux, Tokens moyens/génération |
| 10.1.2 | Vérifier la légende/aide des cartes | Chaque carte a un tooltip explicatif décrivant ce qu'elle mesure |
| 10.1.3 | Vérifier que « Générations sans erreur » = nombre de générations qui ont réussi au **premier** essai | Correspondance avec les générations observées |
| 10.1.4 | Générer un exercice qui provoque une erreur sandbox puis est corrigé automatiquement par le retry | Le compteur « Erreurs corrigées (retry) » augmente de 1 |
| 10.1.5 | Vérifier que les générations sans erreur affichent le bon nombre (ex. 6 exercices générés sans retry → compteur = 6) | Pas d'inversion entre « sans erreur » et « retry » |

### 10.2 Filtrage par plage de dates
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 10.2.1 | Cliquer sur « 7 derniers jours » | Les statistiques couvrent les 7 derniers jours |
| 10.2.2 | Cliquer sur « 30 derniers jours » | Les statistiques couvrent les 30 derniers jours |
| 10.2.3 | Cliquer sur « 365 derniers jours » | Les statistiques couvrent l'année en cours |
| 10.2.4 | 🔢 Saisir une plage personnalisée : Du `2026-01-01` Au `2026-01-31` | Les statistiques affichent uniquement les données de janvier 2026 |
| 10.2.5 | Saisir une plage sans données | Les compteurs affichent 0, le graphique est vide ou indique l'absence de données |

### 10.3 Graphique journalier
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 10.3.1 | Vérifier le graphique journalier dans les statistiques | Le graphique affiche une courbe ou des barres par jour avec les métriques correspondantes |
| 10.3.2 | Supprimer toutes les conversations et recharger les statistiques | Les tokens totaux (entrée, sortie) et le temps de réponse moyen reviennent à 0 / N/A |

---

## 11. Administration — Configuration

### 11.1 Sélecteur LLM
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 11.1.1 | Naviguer vers Administration → onglet « Configuration » | La section de sélection du LLM s'affiche avec le fournisseur et modèle actuels |
| 11.1.2 | Ouvrir le menu déroulant du LLM | La liste des fournisseurs/modèles disponibles s'affiche |
| 11.1.3 | Sélectionner un LLM différent et cliquer sur « Enregistrer » | Un message de succès s'affiche. Le nouveau LLM est utilisé pour les générations suivantes |
| 11.1.4 | Recharger la page et revenir dans la configuration | Le LLM sélectionné est persistent — le même est affiché |

### 11.2 Paramètres d'exécution
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 11.2.1 | Vérifier la présence des paramètres configurables : Température, Nombre max de tentatives, Timeout sandbox, Limite de fichiers joints, Seuil de score template, etc. | Tous les paramètres sont visibles avec leur description et valeur actuelle |
| 11.2.2 | 🔢 Modifier la température à `0.5` et sauvegarder | Le message de succès s'affiche. La nouvelle valeur est sauvegardée |
| 11.2.3 | 🔢 Modifier le seuil de score template (`TEMPLATE_SCORE_THRESHOLD`) à `0.95` | La modification est sauvegardée. Les nouvelles générations utiliseront ce seuil plus strict pour déclencher la génération par template |
| 11.2.4 | Tenter de saisir une valeur hors plage (ex. température = `5.0`) | Un message d'erreur s'affiche indiquant la valeur max autorisée |
| 11.2.5 | Cliquer sur « Annuler » après avoir modifié un paramètre sans sauvegarder | Les modifications sont annulées et les valeurs originales sont restaurées |

### 11.3 Section modèle d'embedding
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 11.3.1 | Vérifier l'affichage de la section « Modèle d'embedding » dans la configuration | La section affiche **uniquement le nom du modèle** (ex. `multilingual-e5-large-instruct`) — **pas** le chemin complet `/opt/models/...` |
| 11.3.2 | Vérifier que les sections obsolètes « Génération d'exercices » et « Discussion (recherche documentaire) » n'apparaissent plus | Ces deux sections sont absentes de la page |

---

## 12. Scénarios de bout en bout (End-to-End)

### 12.1 Parcours enseignant complet
> 👤 Compte `prof_test`

| # | Action | Résultat attendu |
|---|--------|-----------------|
| 12.1.1 | Se connecter, générer un exercice de mathématiques sur les fractions (mode exercice personnalisé), l'enrichir avec 2 modifications itératives, le prévisualiser, remplir les métadonnées et le publier sur le cercle personnel | L'exercice est publié avec succès sur PLaTon avec toutes les métadonnées remplies |

### 12.2 Parcours administrateur — surveillance
> 👤 Compte `admin_test`

| # | Action | Résultat attendu |
|---|--------|-----------------|
| 12.2.1 | Générer un exercice en tant qu'admin (mode personnalisé), accéder aux journaux et vérifier que la conversation courante apparaît avec tous les détails (étape RAG, sélection composants, génération LLM, tokens) | La conversation est visible avec tous les détails de la génération |
| 12.2.2 | Depuis les statistiques, vérifier que le compteur d'exercices publiés, de conversations, de générations sans erreur sont cohérents avec les actions effectuées | Les statistiques sont exactes et mises à jour |

### 12.3 Génération par template avec vérification des logs
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 12.3.1 | Générer un exercice qui sélectionne automatiquement un template (pas d'option personnalisé) | L'exercice est généré via template |
| 12.3.2 | Accéder aux journaux et vérifier que la conversation et l'utilisateur sont correctement associés à cette génération | La génération template n'apparaît pas comme « orpheline » — l'utilisateur et la conversation sont bien enregistrés |

### 12.4 Test de robustesse — rechargement de page pendant une génération
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 12.4.1 | Lancer une génération et recharger la page (F5) pendant qu'elle est en cours | La génération est interrompue côté client. Après rechargement, l'exercice est dans son état précédent (ou vide si c'était la première génération) |

---

## 13. Accessibilité et UX

### 13.1 Messages d'état vides
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 13.1.1 | Supprimer toutes les conversations dans les journaux | Le message « Aucune conversation enregistrée » s'affiche **centré** au milieu de la zone de liste |
| 13.1.2 | Avec des conversations existantes, appliquer un filtre de dates qui exclut tout | Le message « Aucune conversation ne correspond aux filtres » s'affiche **en dessous** de la barre de recherche et des filtres — **pas** au milieu de la page |

### 13.2 Comportement du header lors du manque d'espace
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 13.2.1 | Ouvrir simultanément le panneau gauche et le panneau droit (exercice et composants) | Les boutons de la barre d'en-tête se réduisent automatiquement à leurs icônes (sans labels texte) dès que l'espace disponible est insuffisant |
| 13.2.2 | Fermer un panneau | Les labels texte réapparaissent dès que l'espace est suffisant |

### 13.3 Animations et indicateurs de chargement
| # | Action | Résultat attendu |
|---|--------|-----------------|
| 13.3.1 | Joindre un fichier et observer | Une animation est visible sur l'icône de fichier pendant le traitement |
| 13.3.2 | Cliquer sur « Publier » | Une animation de chargement s'affiche sur le bouton. Le bouton est désactivé pour éviter les doubles publications |
| 13.3.3 | Lancer une génération et observer la barre de progression | La timeline de génération (sélection composants → RAG → LLM → sandbox) est visible dans la discussion |

