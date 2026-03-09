# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versioning scheme follows [Semantic Versioning](https://semver.org/).

---

## [v1.0.0-rc.1] — 2026-03-09

### Added

- Exercise generation workspace with conversational interface (SSE streaming).
- RAG-based template selection and pure exercise generation modes.
- Automatic PLaTon component selection via LLM, with manual override.
- Sandbox validation with automatic correction retry loop.
- Exercise publication to PLaTon directly from the workspace.
- File attachment support (PDF, DOCX) as generation context.
- Workspace autosave and onboarding tour.
- PLaTon documentation Q&A mode (discussion panel).
- Admin dashboard with usage statistics and charts.
- Runtime configuration panel (no restart required).
- Full generation log viewer with conversation grouping and statistics.
- PLaTon OAuth authentication with Redis-backed sessions.
- Automatic database schema migration on startup.
- Background PLaTon resource synchronisation with daily refresh.
- Docker-based deployment with GitHub Actions CI/CD pipeline.

### Fixed

- Administration page was accessible to non-administrator accounts (`c7dd549`).
- Non-existent Cerebras model reference caused a silent failure in provider selection (`c97402b`).
- Docker Compose image tag misconfiguration in production (`e48612b`).
- Incorrect Docker registry login username in the deployment workflow (`a6b96e3`).
- Various visual and functional defects from internal testing (`ed83986`).
