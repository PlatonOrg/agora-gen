# Problèmes connus et améliorations — Agora AI Agent

## 1. Problèmes connus

### 1.1 Fonctionnels

| # | Problème | Priorité | Détail |
|---|----------|----------|--------|
| 1 | **Qualité des exercices générés** | Haute | La qualité dépend fortement du prompt et du modèle LLM. Certains exercices complexes nécessitent plusieurs itérations de correction manuelle. |
| 2 | **Templates à variables limitées** | Moyenne | La génération basée sur les templates ne modifie que les variables `config_variables` ; les modifications structurelles profondes (ajout de composants, modification du builder) ne sont pas possibles via template. |
| 3 | **SSE et déconnexion réseau** | Moyenne | Si la connexion réseau est interrompue pendant une génération SSE, le client ne reçoit plus les événements mais la génération continue côté serveur. L'état de l'exercice peut alors être incohérent. |
| 4 | **Cache navigateur** | Basse | L'état de la conversation est stocké dans le localStorage. En cas de corruption, un reset manuel est nécessaire (vider le localStorage). |
| 5 | **Performances RAG** | Moyenne | Le temps de recherche vectorielle peut être élevé avec un grand nombre d'exercices indexés. Pagination et limite de résultats sont en place mais pourraient être optimisées. |
| 6 | **Mise à jour automatique ne supprime pas** | Moyenne | La synchronisation automatique quotidienne des ressources PLaTon détecte les ajouts et modifications, mais **ne supprime pas** les ressources retirées de PLaTon. Un exercice supprimé côté PLaTon reste présent dans la base locale et peut continuer à être proposé comme exemple RAG ou template. Un nettoyage manuel de la base est nécessaire pour corriger cela. |
| 7 | **Pas de support des fichiers binaires** | Haute | La fonctionnalité de pièces jointes (chat) ne supporte que les documents textuels (`.txt`, `.md`, `.py`, `.html`, etc.). Les fichiers binaires (images, PDF, Word, archives, etc.) sont explicitement rejetés. Aucune extraction de texte depuis des formats binaires n'est implémentée. |
| 8 | **Absence de RAG et de sélection de composants lors des modifications** | Haute | Lorsque l'exercice n'est pas vide (requêtes suivantes — modification), le workflow saute entièrement la recherche RAG et la sélection de composants. Cela peut poser problème : si l'utilisateur ajoute manuellement un titre ou un composant, puis demande une génération, le LLM ne reçoit ni exemples d'exercices similaires ni documentation de composants contextuelle. La génération peut alors produire un résultat de qualité inférieure ou incohérent avec les composants présents dans l'exercice. |
| 9 | **Exercices exemples tronqués** | Moyenne | Les exercices fournis comme exemples au LLM sont tronqués avant injection dans le prompt (champs principaux limités à 700 caractères, autres champs à 200 caractères). Pour des exercices complexes avec du code long, le LLM ne voit qu'une version partielle des exemples, ce qui peut nuire à la qualité de la génération par imitation. |
| 10 | **Nouveau composant PLaTon nécessite une documentation manuelle** | Haute | Lorsqu'un nouveau composant est ajouté dans PLaTon, il ne devient utilisable par Agora que si sa page de documentation `.mdx` respecte exactement le format attendu (frontmatter `title`/`description`, H1, section `## Documentation`, section `## API` avec `<ComponentProperties schema={...} />`). Tout composant dont la documentation est absente ou mal formatée sera ignoré par le builder de métadonnées et ne sera jamais proposé ni documenté pour le LLM. Il peut aussi être nécessaire de créer un fichier de prompt dédié dans `resources/prompts/system_prompts/` si le composant requiert des instructions de génération spécifiques. Voir la section correspondante dans le `MANUEL_DEVELOPPEUR.md` pour le processus complet. |

### 1.2 Techniques

| # | Problème | Priorité | Détail |
|---|----------|----------|--------|
| 1 | **Gestion mémoire des fichiers** | Moyenne | Les fichiers uploadés sont stockés dans Redis avec un TTL de session. En cas de crash Redis, les fichiers en attente sont perdus. |
| 2 | **Absence de tests E2E** | Haute | Il n'y a pas de suite de tests end-to-end automatisés couvrant le flux complet (UI → backend → LLM → sandbox). |
| 3 | **Migration de base de données** | Haute | L'application ne dispose pas d'un outil de migration (Alembic). Les changements de schéma doivent être appliqués manuellement. |
| 4 | **Monitoring en production** | Moyenne | Pas de monitoring applicatif centralisé (health checks, alertes, métriques Prometheus). |

---

## 2. Améliorations proposées

### 2.1 Court terme

| # | Amélioration | Impact | Effort |
|---|-------------|--------|--------|
| 1 | **Alembic pour les migrations** | Fiabilité des déploiements | 2-3 jours |
| 2 | **Tests E2E avec Playwright** | Qualité, non-régression | 1 semaine |
| 3 | **Monitoring Prometheus + Grafana** | Observabilité production | 3-5 jours |
| 4 | **Retry SSE côté client** | Résilience réseau | 1-2 jours |
| 5 | **Pagination côté serveur pour les logs** | Performance avec volume | 2-3 jours |
| 6 | **Suppression des ressources obsolètes lors de la sync** | Cohérence des données RAG | 2-3 jours |
| 7 | **Support extraction texte depuis PDF/Word** | Qualité des pièces jointes | 3-5 jours |
| 8 | **RAG et sélection de composants lors des modifications** | Qualité des générations de modification | 3-5 jours |

### 2.2 Moyen terme

| # | Amélioration | Impact | Effort |
|---|-------------|--------|--------|
| 1 | **Versioning des exercices** | Traçabilité des modifications | 1-2 semaines |
| 2 | **Multi-utilisateurs en temps réel** | Collaboration | 2-3 semaines |
| 3 | **Export/Import d'exercices** | Portabilité | 3-5 jours |
| 4 | **Système de feedback utilisateur** | Amélioration qualité prompts | 1 semaine |
| 5 | **Indexation RAG incrémentale** | Performance, fraîcheur données | 1 semaine |

### 2.3 Long terme

| # | Amélioration | Impact | Effort |
|---|-------------|--------|--------|
| 1 | **Fine-tuning du modèle** | Qualité de génération | Variable |
| 2 | **Agent multi-étapes autonome** | Exercices complexes | 3-4 semaines |
| 3 | **Support multi-langues** | Internationalisation | 2 semaines |
| 4 | **Mode hors-ligne** | Utilisation sans connexion | 3-4 semaines |

---

## 3. Dette technique

- Certains composants Angular utilisent encore des patterns impératifs (Promises) au lieu de signaux
- Le fichier `workflow.py` est volumineux (~855 lignes) et pourrait être découpé en modules plus petits
- Les prompts système sont stockés en fichiers texte sans versioning sémantique
- Pas de validation de schéma côté base de données pour les colonnes JSON
- Le frontend ne gère pas l'expiration de session de manière proactive (pas de refresh token)
