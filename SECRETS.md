# GitHub Secrets Configuration

This document lists every secret required by the CI/CD pipeline.
All secrets are configured in one of two places:

- **Repository secrets:** GitHub > Repository > Settings > Secrets and variables > Actions > New repository secret
- **Environment secrets:** GitHub > Repository > Settings > Environments > production > Add secret

---

## Repository Secrets

These are available to all jobs in the pipeline.

### `VPS_HOST`
The public IP address or domain name of your production server.

- **Example value:** `192.168.1.100` or `agora.example.com`
- **Where to find it:** Your VPS provider dashboard (Hetzner, OVH, DigitalOcean, etc.) under the server's network details.

---

### `VPS_USER`
The Linux username used to connect to the VPS via SSH.

- **Example value:** `ubuntu`, `root`, or `agora`
- **Where to find it:** Defined when you created the VPS, or check with `whoami` on the server.

---

### `VPS_SSH_KEY`
The **private** SSH key that grants access to the VPS. The corresponding public key must already be present in `~/.ssh/authorized_keys` on the server.

- **Example value:** The full contents of your `~/.ssh/id_ed25519` (or `id_rsa`) file, including the `-----BEGIN` and `-----END` lines.
- **Where to find it:** On your local machine, run:
  ```bash
  cat ~/.ssh/id_ed25519
  ```
  If you do not have a key pair, generate one:
  ```bash
  ssh-keygen -t ed25519 -C "github-actions-deploy"
  # Then add the public key to the server:
  ssh-copy-id -i ~/.ssh/id_ed25519.pub YOUR_USER@YOUR_VPS_HOST
  ```

---

### `GH_PAT`
A GitHub Personal Access Token (PAT) with permission to pull images from the GitHub Container Registry (GHCR) on the VPS. This is separate from `GITHUB_TOKEN` because `GITHUB_TOKEN` only exists inside the GitHub Actions runner, not on your VPS.

- **Required scope:** `read:packages` only (principle of least privilege).
- **Where to create it:**
  1. GitHub > Your profile avatar (top right) > Settings
  2. Developer settings > Personal access tokens > Tokens (classic)
  3. Generate new token (classic)
  4. Select scope: `read:packages`
  5. Copy the token value immediately — it is only shown once.

  > If the repository is owned by an organization, the token must belong to an account that is a member of that organization.

---

### `ENV_PROD`
The full contents of your `.env.prod` file. The pipeline writes this to the VPS at deploy time and never stores it on disk in the repository.
---

## Environment Secrets (production environment)

These secrets are scoped to the `production` environment and are only available to the `deploy` job. This allows you to add protection rules (required reviewers, wait timers) before any deployment runs.

There are no additional secret values for this environment beyond those listed above — the same secrets are referenced. The environment gate simply controls **when** the deploy job is allowed to run.

To configure protection rules:
1. GitHub > Repository > Settings > Environments > production
2. Enable "Required reviewers" and add yourself or a teammate.
3. Optionally set a "Wait timer" (e.g. 5 minutes) to allow cancellation before deployment begins.

---

## Summary Table

| Secret name | Scope | Sensitivity |
|---|---|---|
| `VPS_HOST` | Repository | Low |
| `VPS_USER` | Repository | Low |
| `VPS_SSH_KEY` | Repository | Critical — never share |
| `GH_PAT` | Repository | High — read:packages only |
| `ENV_PROD` | Repository | Critical — contains all credentials |

