import { TourStep } from '../services/onboarding.service';

export const WORKSPACE_TOUR_STEPS: TourStep[] = [
  {
    id: 'welcome',
    title: 'Bienvenue sur Agora',
    body: 'Agora est votre espace de création d\'exercices interactifs pour la plateforme <strong>PLaTon</strong>. Ce guide rapide vous présente chaque section de l\'interface en moins de 2 minutes.',
    targetSelector: '.workspace-container',
    position: 'bottom',
  },
  {
    id: 'panel-menu',
    title: 'Afficher / masquer le panneau',
    body: 'Ce bouton affiche ou masque le panneau latéral gauche. Le panneau contient la <strong>Discussion</strong> avec l\'IA et la <strong>Bibliothèque de modèles</strong>. Utilisez le menu hamburger dans l\'en-tête du panneau pour basculer entre les deux.',
    targetSelector: '.header-btn--toggle-panel',
    position: 'bottom',
  },
  {
    id: 'discussion',
    title: 'Discussion avec l\'IA',
    body: 'Dialoguez avec l\'assistant. Deux modes : <strong>Discuter</strong> pour poser des questions sur PLaTon, et <strong>Générer</strong> pour créer ou modifier un exercice. Cliquez sur le bouton <strong>?</strong> dans l\'en-tête pour obtenir des conseils de rédaction de prompts.',
    targetSelector: '.left-panel-content:not(.left-panel-content--hidden)',
    position: 'right',
  },
  {
    id: 'templates',
    title: 'Bibliothèque de modèles',
    body: 'Parcourez des centaines de modèles d\'exercices existants. Filtrez par <strong>composant</strong>, <strong>sujet</strong>, <strong>niveau</strong> ou <strong>cercle</strong>, puis appliquez un modèle en un clic. Cliquez sur <strong>?</strong> dans l\'en-tête pour comprendre les modèles.',
    targetSelector: '.left-panel-content:not(.left-panel-content--hidden)',
    position: 'right',
  },
  {
    id: 'exercise-editor',
    title: 'Éditeur d\'exercice',
    body: 'La zone centrale est votre espace de travail : <strong>titre</strong>, <strong>énoncé</strong>, <strong>composants interactifs</strong>, <strong>indications</strong> et <strong>théories</strong>. Les boutons en haut permettent de <strong>prévisualiser</strong> l\'exercice ou d\'en consulter le <strong>code PLE</strong>.',
    targetSelector: '.content-panel',
    position: 'left',
  },
  {
    id: 'components-panel',
    title: 'Panneau Composants',
    body: 'Tous les composants interactifs PLaTon sont listés ici : <strong>formulaires</strong> (QCM, saisie, match…) et <strong>widgets</strong> (graphes, automates…). Survolez un composant pour voir sa description.',
    targetSelector: '.side-panel__body',
    position: 'left',
  },
  {
    id: 'drag-drop',
    title: 'Glisser-déposer',
    body: 'Faites glisser un composant vers <strong>l\'éditeur</strong> pour l\'ajouter directement, ou vers la <strong>zone de discussion</strong> pour demander à l\'IA de l\'intégrer dans la génération.',
    targetSelector: '.drag-guide',
    position: 'left',
  },
  {
    id: 'header-actions',
    title: 'Actions rapides',
    body: '<strong>Prévisualiser</strong> lance un aperçu dans PLaTon, <strong>Code PLE</strong> affiche le source, <strong>Publier</strong> envoie l\'exercice. Le bouton rouge <strong>Réinitialiser</strong> efface tout.',
    targetSelector: '.header-actions',
    position: 'bottom',
  },
  {
    id: 'finish',
    title: 'Vous êtes prêt !',
    body: 'Retrouvez ce guide à tout moment via le bouton <strong>Guide</strong> dans la barre d\'en-tête.',
    targetSelector: '.workspace-container',
    position: 'bottom',
  },
];

export const DISCUSSION_HELP_CONTENT = `
## Utiliser le panneau Discussion

### Les deux modes

**Discuter** — Posez des questions sur la plateforme PLaTon, ses composants et sa documentation. L'IA s'appuie sur la documentation officielle pour répondre avec précision.

**Générer** — Demandez à l'IA de créer ou modifier un exercice. Le résultat s'applique directement dans l'éditeur central.

---

### Glisser-déposer dans la zone de saisie

Faites glisser directement dans la zone de saisie :
- un **composant** depuis le panneau Composants (à droite) pour demander à l'IA de l'utiliser
- un **paramètre de modèle** (depuis les paramètres d'un modèle appliqué) pour le contextualiser
- un **champ d'exercice** (titre, énoncé…) pour cibler une modification précise
- un **fichier** (image, données) si votre configuration LLM le supporte

---

### Rédiger un prompt efficace

Pour obtenir des résultats optimaux, structurez votre demande dans cet ordre :

1. **Glissez les composants souhaités** dans la zone de saisie
2. **Précisez la matière** (mathématiques, informatique, physique, algorithmique…)
3. **Indiquez le niveau et l'année** (Terminale, L1, M2, CPGE…)
4. **Décrivez le contenu** (notion abordée, objectif pédagogique, type d'exercice)
5. **Ajoutez des contraintes** (durée, difficulté souhaitée, nombre de questions, exemples de données)

---

### Exemples de prompts efficaces

> *Génère un exercice de tri de tableau pour des étudiants en L1 informatique. Utilise un composant formulaire avec plusieurs étapes de validation.*

> *Crée un QCM sur les intégrales de Riemann pour des étudiants de Terminale, avec 4 propositions dont une seule est correcte.*

> *Modifie l'énoncé de l'exercice actuel pour ajouter un exemple concret sur les listes chaînées.*

---

### Option : Exercice entièrement personnalisé

Activez le toggle **"Exercice entièrement personnalisé"** si vous souhaitez que l'IA crée l'exercice depuis zéro, sans s'appuyer sur un modèle de la bibliothèque. Ce mode offre le plus de liberté créative.

---

### Recommandations

> Plus votre description est précise, plus le résultat sera conforme à vos attentes. Donnez toujours un contexte pédagogique clair : matière, niveau, objectif.
`;

export const TEMPLATES_HELP_CONTENT = `
## Qu'est-ce qu'un modèle PLaTon ?

Un **modèle** est un exercice pré-construit, validé et réutilisable. Il encapsule la structure de l'exercice (composants interactifs, logique de correction, mise en page) et expose des **paramètres** personnalisables sans modifier le code source.

---

### Les paramètres d'un modèle

Chaque modèle définit ses propres paramètres. Ces paramètres varient d'un modèle à l'autre et permettent de **personnaliser le contenu** de l'exercice sans toucher à sa structure.

Par exemple, un modèle de QCM pourra exposer des paramètres pour les questions, les propositions et le nombre de bonnes réponses, tandis qu'un modèle d'exercice de programmation pourra exposer des paramètres pour le langage, le code initial et les tests.

Lorsque vous appliquez un modèle, ses paramètres apparaissent dans l'éditeur central et vous pouvez les modifier directement ou demander à l'IA de les adapter.

---

### Comment utiliser un modèle ?

1. **Recherchez** par mots-clés, composant, sujet, niveau ou cercle pédagogique
2. **Affinez** les résultats avec les filtres avancés
3. **Cliquez** sur un résultat pour consulter ses détails et paramètres
4. **Appliquez** le modèle — les champs de l'éditeur se remplissent automatiquement
5. **Personnalisez** les paramètres dans l'éditeur, ou demandez à l'IA de les adapter

---

### Modèle vs exercice personnalisé

- Un **modèle** fournit une base solide et testée, idéale pour démarrer rapidement avec une structure éprouvée.
- Un **exercice personnalisé** (mode "Générer" avec l'option libre activée) est entièrement créé par l'IA selon votre description.

Les deux approches sont complémentaires : commencez avec un modèle existant, puis affinez avec l'IA pour l'adapter à vos besoins spécifiques.
`;

