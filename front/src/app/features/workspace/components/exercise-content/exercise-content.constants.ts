export const FIELD_DESCRIPTIONS: Record<string, string> = {
  titre: "Titre affiché à l'étudiant en haut de l'exercice. Il doit être court, précis et refléter le sujet traité.",
  enonce: "Texte principal de l'exercice présenté à l'étudiant. Décrit la situation, pose la question et fournit toutes les informations nécessaires pour répondre. Supporte la syntaxe Markdown et LaTeX.",
  forme: "Disposition du formulaire de réponse : indique l'ordre et la manière dont les composants interactifs (champs, boutons, etc.) sont affichés à l'étudiant. Utilise la notation PLaTon {{nom_composant}}.",
  solution: "Corrigé de l'exercice affiché à l'étudiant après soumission ou à sa demande. Peut contenir une démarche de résolution détaillée. Supporte Markdown et LaTeX.",
  composants: "Éléments interactifs utilisés dans l'exercice : champs de saisie, boutons, zones de feedback, etc. Chaque composant correspond à une variable accessible dans le builder et le grader.",
  indications: "Indices ou conseils optionnels débloqués progressivement par l'étudiant lorsqu'il est bloqué. Permet de guider sans donner directement la réponse.",
  theories: "Ressources pédagogiques complémentaires (cours, articles, vidéos) accessibles depuis l'exercice. Chaque ressource possède un titre et une URL.",
  sandbox: "Environnement d'exécution du code de l'exercice. Python est recommandé pour les exercices scientifiques ; Node.js pour les exercices orientés web ou algorithmique JavaScript.",
  construction: "Script d'initialisation de l'exercice (builder) : génère les données aléatoires, initialise les composants et prépare les variables à évaluer. S'exécute à chaque ouverture de l'exercice.",
  evaluation: "Script de correction (grader) : évalue la réponse de l'étudiant, calcule le score et produit un feedback personnalisé. S'exécute à chaque soumission.",
  sandbox_variables: "Variables supplémentaires accessibles dans les scripts builder et grader. Permettent de passer des paramètres globaux à l'exercice (constantes, configurations, etc.).",
  topics: "Thèmes ou disciplines associés à l'exercice (ex. : Algèbre, Probabilités, Algorithmique). Facilitent la recherche et l'organisation dans la bibliothèque PLaTon.",
  levels: "Niveaux scolaires ou de difficulté associés (ex. : Licence 1, Avancé, Débutant). Permettent de cibler le public approprié lors de la recherche.",
  readme: "Documentation de l'exercice au format Markdown. Affichée aux enseignants dans la bibliothèque PLaTon. Décrit l'objectif pédagogique, les prérequis, et les consignes de personnalisation.",
};

export function makeMonacoOptions(language: string, readOnly = false): object {
  return {
    theme: 'vs',
    language,
    automaticLayout: true,
    minimap: { enabled: false },
    readOnly,
  };
}

export const PLE_EDITOR_OPTIONS = {
  theme: 'vs',
  language: 'plaintext',
  automaticLayout: true,
  minimap: { enabled: false },
  readOnly: true,
  fontSize: 14,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  wordWrap: 'on',
};

export const SANDBOX_LANGUAGE_MAP: Record<string, string> = {
  python: 'python',
  node: 'javascript',
};


