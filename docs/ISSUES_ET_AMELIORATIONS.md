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
- Le fichier `workflow.py` est volumineux (~850 lignes) et pourrait être découpé en modules plus petits
- Les prompts système sont stockés en fichiers texte sans versioning sémantique
- Pas de validation de schéma côté base de données pour les colonnes JSON
- Le frontend ne gère pas l'expiration de session de manière proactive (pas de refresh token)

