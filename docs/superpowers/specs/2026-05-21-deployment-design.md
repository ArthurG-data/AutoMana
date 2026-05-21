# Deployment Design — AutoMana

**Date:** 2026-05-21
**Status:** Approved
**Scope:** Branching model, CI/CD, VPS setup, TLS, DB redundancy, and cloud migration path

---

## 1. Goals

- Ship AutoMana to a production environment accessible over HTTPS with a real domain
- Run tests automatically before any merge to `main`
- Deploy automatically on every merge to `main` (zero manual steps)
- Protect Postgres data against disk/server failure from day one
- Design so migrating to managed cloud services later is low-friction

## 2. Branching Model

Two long-lived branches:

| Branch | Role | Protection |
|--------|------|------------|
| `main` | Production | Protected — no direct pushes. Requires PR from `dev`. Every merge triggers a deploy. |
| `dev` | Integration | Default branch for feature work. All PRs from `feat/*`, `fix/*`, `refactor/*` target `dev`. |

**Flow:**

```
feat/my-feature  ──PR──►  dev  ──PR──►  main
                           ↑              ↑
                        CI tests      CI tests + deploy
```

**Migration from current state:**
1. Create `dev` branch from `main`
2. Set `dev` as the default branch in GitHub
3. Enable branch protection on `main` (require PR, require status checks to pass)
4. All in-flight feature branches re-target `dev` instead of `main`

## 3. CI/CD Pipeline

### 3.1 Workflow: `ci.yml`

**Triggers:** pull_request targeting `dev` or `main`; push to `dev`

**Steps:**
1. Checkout code
2. Build and start services with `docker compose -f deploy/docker-compose.test.yml up -d`
3. Wait for health checks
4. Run `pytest` (backend tests)
5. Tear down services

**Gate:** PRs to `dev` and `main` cannot merge if this workflow fails.

### 3.2 Workflow: `deploy.yml`

**Triggers:** push to `main` (i.e., after a PR merge)

**Steps:**
1. Re-run CI tests (same as above — deploy only proceeds if tests pass)
2. SSH into the production VPS using a deploy key
3. On the VPS, run:
   ```bash
   cd /opt/automana
   git pull origin main
   docker compose -f deploy/docker-compose.prod.yml up -d --build
   ```
4. Smoke test: `curl -f https://<PROD_DOMAIN>/health`
5. Report success or failure as a GitHub Actions job status

**GitHub Secrets required:**

| Secret | Value |
|--------|-------|
| `VPS_SSH_KEY` | Private SSH key for the `deploy` user on the VPS |
| `VPS_HOST` | IP address of the production VPS |
| `VPS_USER` | Linux user used for deployment (e.g., `deploy`) |

**Secret rotation:** Rotate `VPS_SSH_KEY` whenever team members leave. The deploy key only needs write access to `/opt/automana` — it does not need sudo.

## 4. VPS Setup

### 4.1 Server

| Attribute | Value |
|-----------|-------|
| Provider | Kamatera |
| Type | 2 vCPU, 4 GB RAM, 50 GB SSD (General Purpose) |
| OS | Ubuntu 24.04 LTS |
| Region | Choose closest to target users (US, EU, or APAC zones available) |
| Cost | ~$4–10/mo depending on zone and specs |

### 4.2 Firewall rules (Kamatera Firewall)

| Port | Protocol | Allow from |
|------|----------|------------|
| 22 | TCP | Your IP only (or IP allowlist) |
| 80 | TCP | Any (redirect to 443) |
| 443 | TCP | Any |

All other ports blocked by default. Postgres (5432) and Redis (6379) are **never** exposed to the public internet — they communicate only on the internal Docker network.

### 4.3 Server bootstrap (one-time)

```bash
# As root on a fresh Ubuntu 24.04 VPS:
apt-get update && apt-get install -y docker.io docker-compose-v2 git certbot
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
mkdir -p /opt/automana && chown deploy:deploy /opt/automana
# Add deploy user's authorized_keys (from GitHub Actions secret)
```

### 4.4 Application directory

The repo is cloned to `/opt/automana` on the VPS. The `deploy` user owns the directory and the GitHub Actions workflow runs `git pull` + `docker compose up` as that user.

## 5. TLS (Let's Encrypt via Certbot)

The current `nginx.prod.conf` uses self-signed certs (`localhost.pem`, `localhost-key.pem`). For production, replace with Let's Encrypt certs.

**Setup (one-time on VPS):**

1. Point your domain's A record to the Hetzner VPS IP
2. Stop nginx container (port 80 must be free for Certbot challenge):
   ```bash
   docker compose -f deploy/docker-compose.prod.yml stop proxy
   ```
3. Issue cert:
   ```bash
   certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com
   ```
4. Certs are written to `/etc/letsencrypt/live/yourdomain.com/`
5. Mount into the nginx container by updating `docker-compose.prod.yml`:
   ```yaml
   proxy:
     volumes:
       - /etc/letsencrypt:/etc/letsencrypt:ro
   ```
6. Update `nginx.prod.conf` to reference:
   ```nginx
   ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
   ```
7. Set up auto-renewal:
   ```bash
   # Certbot installs a systemd timer automatically; verify:
   systemctl status certbot.timer
   # The renewal hook should reload nginx:
   echo "docker compose -f /opt/automana/deploy/docker-compose.prod.yml exec proxy nginx -s reload" \
     > /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh
   chmod +x /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh
   ```

**Dev tunnel:** The frp relay at `103.6.171.115` (Caddy + frps) remains unchanged and is used only for the `dev` environment.

## 6. Database Redundancy

### 6.1 Layer 1 — Dedicated disk for Postgres data (protect against disk/server loss)

On Kamatera, attach an additional block disk to the VPS via the Kamatera console and mount it as the Postgres data directory. This separates the DB data from the OS disk so data survives server rebuilds.

```bash
# On VPS, after attaching a second disk (e.g., /dev/vdb) and formatting/mounting at /mnt/postgres-data:
mkdir -p /mnt/postgres-data/pgdata
chown -R 999:999 /mnt/postgres-data/pgdata  # postgres container UID
```

Update `docker-compose.prod.yml` to use the bind mount:

```yaml
postgres:
  volumes:
    - /mnt/postgres-data/pgdata:/var/lib/postgresql/data
```

If the VPS is rebuilt, the Postgres disk can be re-attached and the data is intact. Take Kamatera disk snapshots (available in their console) as an additional local backup.

**Cost:** Additional 50 GB disk on Kamatera is ~$3-5/mo.

### 6.2 Layer 2 — Off-site pg_dump to Backblaze B2

Extend the existing `db-backup-prod` container to upload dumps to Backblaze B2 using `rclone`.

```bash
# In the backup script, after pg_dump:
rclone copy /backups/ b2:automana-backups/postgres/ \
  --min-age 1h \
  --b2-account "$B2_ACCOUNT_ID" \
  --b2-key "$B2_APPLICATION_KEY"
# Keep only 7 most recent on B2
rclone delete b2:automana-backups/postgres/ --min-age 7d
```

**Cost:** Backblaze B2 free tier includes 10 GB storage. A typical pg_dump of this DB (card catalog + pricing history) is likely 2–5 GB compressed, so this is essentially free.

**New env vars required in `.env.prod`:**

```
B2_ACCOUNT_ID=...
B2_APPLICATION_KEY=...
```

### 6.3 Layer 3 — Timescale Cloud (future, when HA is needed)

When real high-availability is required (automatic failover, streaming replication), migrate Postgres to **Timescale Cloud** — the only fully managed service that natively supports both TimescaleDB and pgvector.

Migration steps at that time:
1. `pg_dump` from self-hosted Postgres
2. `pg_restore` into Timescale Cloud instance
3. Update `POSTGRES_HOST`, `POSTGRES_PORT`, `DB_PASSWORD` in `.env.prod`
4. Remove the `postgres` and `db-backup-prod` services from `docker-compose.prod.yml`

This is a future milestone, not part of the current implementation.

## 7. Cloud Migration Roadmap (future, not now)

Ordered steps when the project outgrows a single VPS:

| Step | Action | Benefit |
|------|--------|---------|
| 1 | Redis → Upstash | No code change, just swap `REDIS_URL`. Removes Redis ops. |
| 2 | Postgres → Timescale Cloud | Managed HA, pgvector + TimescaleDB native. ~$30-50/mo. |
| 3 | App containers → AWS ECS or Azure Container Apps | Auto-scaling, rolling deploys, no Docker Compose needed. |
| 4 | nginx → cloud load balancer (ALB/Azure Front Door) | TLS managed by cloud, global CDN possible. |

At step 3, the GitHub Actions `deploy.yml` workflow is replaced by an ECS task definition update or an Azure Container Apps revision. The application code changes nothing.

## 8. Out of Scope

- Kubernetes — overkill for this project size
- Multi-region — not needed until significant user growth
- Staging environment — tests run in CI via `docker-compose.test.yml`; no separate staging server
- Blue/green deployments — `docker compose up -d` with health checks is sufficient; add blue/green at step 3 if needed
