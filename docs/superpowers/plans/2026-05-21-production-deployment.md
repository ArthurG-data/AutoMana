# Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy AutoMana to a live Kamatera VPS with GitHub Actions CI/CD, HTTPS via Let's Encrypt, and Postgres data protected by a dedicated disk + Backblaze B2 off-site backups.

**Architecture:** Two GitHub Actions workflows: `ci.yml` runs unit tests on every PR; `deploy.yml` SSHs into the Kamatera VPS on every push to `main` and runs `docker compose up -d --build`. Postgres data lives on a dedicated Kamatera block disk (survives VPS rebuilds). pg_dump runs nightly and uploads to Backblaze B2 via rclone.

**Tech Stack:** GitHub Actions, appleboy/ssh-action, Docker Compose v2, Certbot (Let's Encrypt), uv (Python), pytest, rclone, Backblaze B2

---

> **PLACEHOLDER RULE:** Every occurrence of `YOUR_DOMAIN` in this plan (e.g., `automana.example.com`) must be replaced with your actual production domain before committing or running commands.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `.github/workflows/ci.yml` | Create | Runs unit tests on PRs targeting `dev` or `main` |
| `.github/workflows/deploy.yml` | Create | SSHs to VPS and runs docker compose on push to `main` |
| `deploy/docker-compose.prod.yml` | Modify | Bind-mount Postgres data, fix healthcheck, add TLS volume mounts, Ollama opt-in profile |
| `deploy/docker/nginx/nginx.prod.conf` | Modify | Replace self-signed cert paths with Let's Encrypt paths |
| `config/env/.env.prod.example` | Modify | Document two new B2 env vars |

---

## Task 1: Create `dev` branch and protect `main`

This sets up the branching model. All future feature work targets `dev`; `main` is prod-only.

**Files:** Git/GitHub operations only (no code files)

- [ ] **Step 1: Create `dev` from current `main`**

```bash
git checkout main
git pull origin main
git checkout -b dev
git push -u origin dev
```

- [ ] **Step 2: Set `dev` as the default branch in GitHub**

```bash
gh repo set-default
gh api repos/{owner}/{repo} -X PATCH -f default_branch=dev
```

Or go to GitHub → Settings → Branches → Default branch → change to `dev`.

- [ ] **Step 3: Protect `main` (require PR + status checks)**

```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  --field required_status_checks='{"strict":true,"contexts":["test"]}' \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":0}' \
  --field restrictions=null
```

> Note: The `contexts` value `"test"` must match the job name in `ci.yml` (defined in Task 2). If you rename the job, update this protection rule.

- [ ] **Step 4: Verify protection**

```bash
gh api repos/{owner}/{repo}/branches/main | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['protected'])"
```

Expected output: `True`

- [ ] **Step 5: Switch your local working branch to `dev`**

```bash
git checkout dev
```

All future feature branches (`feat/*`, `fix/*`) branch off `dev` and PR back to `dev`.

---

## Task 2: Write CI workflow

Runs unit tests (mock-based, no DB needed) on every PR targeting `dev` or `main` and on every push to `dev`. Uses `uv` which is already used in the project Dockerfile.

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflows directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write `ci.yml`**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev, main]

jobs:
  test:
    name: test
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "latest"
          enable-cache: true

      - name: Install dependencies
        run: uv sync --frozen --extra dev

      - name: Run unit tests
        run: uv run pytest -v --tb=short
```

> **Why unit tests only:** Integration tests require a live Postgres + Redis. The unit tests use `AsyncMock` throughout and run without any infrastructure. Integration tests can be added to CI later with a service container setup.

> **Job name matters:** The job is named `test`. This must match the `contexts` value in the branch protection rule set in Task 1.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add CI workflow for unit tests"
```

- [ ] **Step 4: Push and verify the workflow appears in GitHub**

```bash
git push origin dev
```

Go to GitHub → Actions → you should see "CI" workflow listed.

---

## Task 3: Write deploy workflow

Triggers on push to `main`. SSHs into the production VPS and runs docker compose to redeploy. Requires GitHub Secrets to be set (see Step 1 below).

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Add GitHub Secrets**

In GitHub → Settings → Secrets and variables → Actions → New repository secret, add three secrets:

| Secret name | Value |
|-------------|-------|
| `VPS_HOST` | IP address of your Kamatera VPS (filled after Task 7) |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Contents of the private SSH key generated in Task 7 |

> You can add these now with placeholder values and update them after Task 7. The deploy workflow won't run until a push to `main` happens.

- [ ] **Step 2: Write `deploy.yml`**

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    name: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "latest"
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --extra dev
      - name: Run unit tests
        run: uv run pytest -v --tb=short

  deploy:
    name: deploy
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to VPS via SSH
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            set -e
            cd /opt/automana
            git pull origin main
            docker compose -f deploy/docker-compose.prod.yml up -d --build
            sleep 5
            curl -fsS https://YOUR_DOMAIN/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('health:', d.get('status', d))"
```

> **Replace `YOUR_DOMAIN`** with your actual domain before committing.

> The `needs: test` ensures deploy only runs if tests pass. The `curl` health check at the end confirms the app is up after deploy. If the health check fails, the deploy job fails and GitHub notifies you.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add deploy workflow (SSH to VPS on main push)"
```

---

## Task 4: Harden `docker-compose.prod.yml`

Four changes in one file:
1. Postgres uses a bind mount to the dedicated disk (not a named Docker volume)
2. Postgres healthcheck fixed (was hardcoded to wrong DB name `manaforge_prod`)
3. Ollama moved to an opt-in profile (won't start unless `--profile gpu` is passed — avoids crash on non-GPU VPS)
4. nginx proxy gets the `/etc/letsencrypt` volume mount for TLS certs

**Files:**
- Modify: `deploy/docker-compose.prod.yml`

- [ ] **Step 1: Fix the Postgres service**

Find the `postgres` service. Replace:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_prod -d manaforge_prod"]
      interval: 5s
      timeout: 3s
      retries: 20
```

With:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready"]
      interval: 5s
      timeout: 3s
      retries: 20
```

And replace the `volumes` block of the `postgres` service:

```yaml
    volumes:
      - pgdata-prod:/var/lib/postgresql/data
      - ../infra/db/init/:/docker-entrypoint-initdb.d/:ro
```

With:

```yaml
    volumes:
      - /mnt/postgres-data/pgdata:/var/lib/postgresql/data
      - ../infra/db/init/:/docker-entrypoint-initdb.d/:ro
```

> The bind mount path `/mnt/postgres-data/pgdata` must exist on the VPS before first startup (created in Task 7). The init scripts only run on first Postgres startup (empty data directory).

- [ ] **Step 2: Add `profiles: [gpu]` to the Ollama service**

Find the `ollama` service and add `profiles`:

```yaml
  ollama:
    profiles: ["gpu"]
    image: ollama/ollama:latest
    container_name: automana-ollama-prod
    restart: unless-stopped
    volumes:
      - /data/ollama:/root/.ollama
    networks:
      - backend-network
    entrypoint: >
      sh -c "ollama serve & sleep 5 && ollama pull qwen3:30b-a3b && wait"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
```

> With `profiles: ["gpu"]`, running `docker compose up -d` will skip Ollama entirely (correct for a CPU-only VPS). To enable it later on a GPU server: `docker compose --profile gpu up -d`.

- [ ] **Step 3: Update the nginx proxy service volumes**

Find the `proxy` service `volumes` block:

```yaml
    volumes:
      - ../config/nginx/certs:/etc/nginx/certs:ro
```

Replace with:

```yaml
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - /var/www/certbot:/var/www/certbot:ro
```

> The first mount gives nginx read access to Let's Encrypt certs. The second mount allows Certbot to place ACME challenge files in `/var/www/certbot` when renewing (nginx serves `/.well-known/acme-challenge/` from this path).

- [ ] **Step 4: Remove the `pgdata-prod` named volume from the top-level `volumes` section**

Find the `volumes:` section at the bottom of the file:

```yaml
volumes:
  pgdata-prod:
  redis-data:
  redis-config:
  flower-data-prod:
```

Remove `pgdata-prod:` from this list:

```yaml
volumes:
  redis-data:
  redis-config:
  flower-data-prod:
```

- [ ] **Step 5: Commit**

```bash
git add deploy/docker-compose.prod.yml
git commit -m "fix(deploy): bind-mount postgres data, fix healthcheck, Ollama GPU profile, Let's Encrypt volumes"
```

---

## Task 5: Update `nginx.prod.conf` for Let's Encrypt

Replace the self-signed cert paths with the Let's Encrypt paths. Also update `server_name` from catch-all `_` to your real domain.

**Files:**
- Modify: `deploy/docker/nginx/nginx.prod.conf`

> **Replace `YOUR_DOMAIN`** throughout this task with your actual domain (e.g., `automana.example.com`).

- [ ] **Step 1: Update the HTTPS server block**

Find in `nginx.prod.conf`:

```nginx
    server {
        listen 443 ssl http2;
        server_name _;

        ssl_certificate     /etc/nginx/certs/localhost.pem;
        ssl_certificate_key /etc/nginx/certs/localhost-key.pem;
```

Replace with:

```nginx
    server {
        listen 443 ssl http2;
        server_name YOUR_DOMAIN;

        ssl_certificate     /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;
```

- [ ] **Step 2: Update the HTTP server block `server_name`**

Find:

```nginx
    server {
        listen 80;
        server_name _;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
```

Replace `server_name _;` with:

```nginx
    server {
        listen 80;
        server_name YOUR_DOMAIN;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
```

- [ ] **Step 3: Commit**

```bash
git add deploy/docker/nginx/nginx.prod.conf
git commit -m "fix(nginx): use Let's Encrypt cert paths for production"
```

---

## Task 6: Extend db-backup-prod for Backblaze B2 upload

The existing `db-backup-prod` service in `docker-compose.prod.yml` runs `pg_dump` on a cron. Extend it to also install `rclone` and upload dumps to Backblaze B2 after each backup, keeping only 7 days of history on B2.

**Files:**
- Modify: `deploy/docker-compose.prod.yml` (the `db-backup-prod` service)
- Modify: `config/env/.env.prod.example` (document the two new env vars)

- [ ] **Step 1: Update `db-backup-prod` environment block**

Find the `db-backup-prod` service `environment:` block:

```yaml
    environment:
      PGPASSWORD: ${POSTGRES_PASSWORD}
      PGHOST: postgres
      PGPORT: 5432
      PGUSER: ${POSTGRES_USER}
      PGDATABASE: ${POSTGRES_DB}
      BACKUP_CRON: ${BACKUP_CRON}  # every 24 hours
```

Replace with:

```yaml
    environment:
      PGPASSWORD: ${POSTGRES_PASSWORD}
      PGHOST: postgres
      PGPORT: 5432
      PGUSER: ${POSTGRES_USER}
      PGDATABASE: ${POSTGRES_DB}
      BACKUP_CRON: ${BACKUP_CRON}
      B2_ACCOUNT_ID: ${B2_ACCOUNT_ID}
      B2_APPLICATION_KEY: ${B2_APPLICATION_KEY}
```

- [ ] **Step 2: Extend the backup command to install rclone and upload to B2**

Find the `db-backup-prod` `command:` block:

```yaml
    command: 
      - |
        apt-get update && apt-get install -y --no-install-recommends cron gzip ca-certificates && \
        mkdir -p /backups && \
        echo "$$BACKUP_CRON root /bin/bash -c 'set -e; ts=\$$(date +%Y%m%d_%H%M%S); pg_dump -Fc -f /backups/\$${PGDATABASE}_\$${ts}.dump \$${PGDATABASE}; ls -1t /backups/*.dump 2>/dev/null | tail -n +7 | xargs -r rm -f'" > /etc/cron.d/pgbackup && \
        chmod 0644 /etc/cron.d/pgbackup && \
        crontab /etc/cron.d/pgbackup && \
        cron -f
```

Replace with:

```yaml
    command: 
      - |
        apt-get update && apt-get install -y --no-install-recommends cron gzip ca-certificates curl unzip && \
        curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip && \
        unzip -q /tmp/rclone.zip -d /tmp && mv /tmp/rclone-*/rclone /usr/local/bin/rclone && rm -rf /tmp/rclone* && \
        mkdir -p /backups && \
        echo "$$BACKUP_CRON root /bin/bash -c '\
          set -e; \
          ts=\$\$(date +%%Y%%m%%d_%%H%%M%%S); \
          pg_dump -Fc -f /backups/\$\${PGDATABASE}_\$\${ts}.dump \$\${PGDATABASE}; \
          ls -1t /backups/*.dump 2>/dev/null | tail -n +7 | xargs -r rm -f; \
          rclone copy /backups/ :b2:automana-backups/postgres/ --b2-account \$\${B2_ACCOUNT_ID} --b2-key \$\${B2_APPLICATION_KEY} --min-age 2h; \
          rclone delete :b2:automana-backups/postgres/ --min-age 7d --b2-account \$\${B2_ACCOUNT_ID} --b2-key \$\${B2_APPLICATION_KEY}'" > /etc/cron.d/pgbackup && \
        chmod 0644 /etc/cron.d/pgbackup && \
        crontab /etc/cron.d/pgbackup && \
        cron -f
```

> `--min-age 2h` on the copy prevents uploading a dump that was just started and isn't finished yet. `rclone delete --min-age 7d` removes B2 objects older than 7 days. The `:b2:` prefix is rclone's "on-the-fly" remote syntax — no config file needed; credentials come from env vars.

- [ ] **Step 3: Document the new vars in `.env.prod.example`**

Open `config/env/.env.prod.example`. Add after the existing backup section:

```bash
# Backblaze B2 — off-site pg_dump upload
# Create a B2 bucket named "automana-backups" and an app key with write access
B2_ACCOUNT_ID=<your-b2-account-id>
B2_APPLICATION_KEY=<your-b2-application-key>
```

- [ ] **Step 4: Commit**

```bash
git add deploy/docker-compose.prod.yml config/env/.env.prod.example
git commit -m "feat(backup): upload pg_dumps to Backblaze B2 via rclone"
```

---

## Task 7: Provision the Kamatera VPS

Manual server setup. Run these commands as root on the freshly created VPS. Nothing gets committed to git here.

**Prerequisite:** Create a server on kamatera.com — Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM, 50 GB OS disk. Note the IP address.

- [ ] **Step 1: SSH in as root and run bootstrap**

```bash
apt-get update && apt-get upgrade -y
apt-get install -y docker.io docker-compose-v2 git certbot
systemctl enable --now docker
```

- [ ] **Step 2: Create the `deploy` user**

```bash
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
mkdir -p /opt/automana
chown deploy:deploy /opt/automana
```

- [ ] **Step 3: Generate an SSH key pair for GitHub Actions**

Run this on your LOCAL machine (not the VPS):

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/automana_deploy -N ""
cat ~/.ssh/automana_deploy.pub   # copy this — goes on the VPS
cat ~/.ssh/automana_deploy       # copy this — goes into GitHub Secret VPS_SSH_KEY
```

- [ ] **Step 4: Install the deploy public key on the VPS**

Back on the VPS, as root:

```bash
mkdir -p /home/deploy/.ssh
echo "PASTE_PUBLIC_KEY_HERE" >> /home/deploy/.ssh/authorized_keys
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
```

- [ ] **Step 5: Update GitHub Secrets**

In GitHub → Settings → Secrets → Actions, update:
- `VPS_HOST` = the VPS IP address
- `VPS_SSH_KEY` = contents of `~/.ssh/automana_deploy` (the private key, starting with `-----BEGIN OPENSSH PRIVATE KEY-----`)

- [ ] **Step 6: Test the SSH connection**

From your local machine:

```bash
ssh -i ~/.ssh/automana_deploy deploy@YOUR_VPS_IP "echo 'SSH OK'"
```

Expected output: `SSH OK`

- [ ] **Step 7: Attach and mount the dedicated Postgres disk**

In the Kamatera console, add a second disk (50 GB) to the VPS. Then on the VPS as root, identify it and format it:

```bash
lsblk   # identify the new disk, likely /dev/vdb or /dev/sdb
```

```bash
# Replace /dev/vdb with the actual device name shown by lsblk
mkfs.ext4 /dev/vdb
mkdir -p /mnt/postgres-data
echo "/dev/vdb /mnt/postgres-data ext4 defaults,nofail 0 2" >> /etc/fstab
mount -a
```

Verify:

```bash
df -h /mnt/postgres-data
```

Expected: shows ~50 GB available.

Create the Postgres data directory with correct ownership:

```bash
mkdir -p /mnt/postgres-data/pgdata
chown -R 999:999 /mnt/postgres-data/pgdata
```

> UID `999` is the default `postgres` user inside the official Postgres Docker image.

- [ ] **Step 8: Set up the firewall**

```bash
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow from YOUR_LOCAL_IP to any port 22 proto tcp   # SSH — replace with your IP
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status
```

> Replace `YOUR_LOCAL_IP` with your actual IP (check via `curl ifconfig.me` on your local machine). If you need SSH from multiple IPs, run `ufw allow from IP to any port 22` for each.

- [ ] **Step 9: Clone the repo onto the VPS**

As the `deploy` user:

```bash
su - deploy
git clone https://github.com/YOUR_GITHUB_ORG/AutoMana.git /opt/automana
cd /opt/automana
git checkout main
```

- [ ] **Step 10: Create `.env.prod` on the VPS**

As the `deploy` user:

```bash
cp /opt/automana/config/env/.env.prod.example /opt/automana/config/env/.env.prod
```

Edit it with real values:

```bash
nano /opt/automana/config/env/.env.prod
```

Minimum values to fill in:

```bash
ENV=prod
POSTGRES_USER=automana_admin
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_DB=automana
APP_BACKEND_DB_USER=app_backend
DB_PASSWORD=<same-as-POSTGRES_PASSWORD-or-app-user-password>
JWT_SECRET_KEY=<run: openssl rand -hex 32>
BACKUP_CRON=0 2 * * *
B2_ACCOUNT_ID=<from Backblaze console>
B2_APPLICATION_KEY=<from Backblaze console>
BROKER_URL=redis://redis:6379/0
REDIS_CACHE_URL=redis://redis:6379/1
FRONTEND_BASE_URL=https://YOUR_DOMAIN
FLOWER_BASIC_AUTH=admin:<strong-password>
```

> Never commit this file. It is gitignored. Keep a secure copy offline.

---

## Task 8: Issue TLS certificate and first deploy

Run on the VPS as `deploy`. Port 80 must be pointing to this VPS (DNS A record set).

**Prerequisite:** Your domain's DNS A record points to the VPS IP. Check with:

```bash
dig +short YOUR_DOMAIN
```

Expected: the VPS IP address.

- [ ] **Step 1: Point your domain DNS to the VPS IP**

In your domain registrar (Namecheap, Cloudflare, etc.), create:
- `A` record: `YOUR_DOMAIN` → `VPS_IP`
- `A` record: `www.YOUR_DOMAIN` → `VPS_IP` (optional)

Wait for DNS propagation (usually 1–5 min on Cloudflare, up to 60 min on others). Verify with `dig +short YOUR_DOMAIN`.

- [ ] **Step 2: Start the stack without TLS first (to verify Docker works)**

```bash
cd /opt/automana

# Temporarily comment out the ssl_certificate lines in nginx.prod.conf is NOT needed —
# instead, run without the proxy to test backend only:
docker compose -f deploy/docker-compose.prod.yml up -d postgres redis celery-worker celery-beat
```

Wait for health checks:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Expected: `postgres`, `redis`, `celery-worker`, `celery-beat` all show `healthy`.

- [ ] **Step 3: Run database initialization**

The init scripts in `infra/db/init/` run automatically on first Postgres startup. Verify:

```bash
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  psql -U automana_admin -d automana -c "\dt" 2>&1 | head -20
```

Expected: lists tables (or empty DB if migrations haven't run yet — that's fine for first boot).

- [ ] **Step 4: Issue the Let's Encrypt certificate**

Certbot `--standalone` temporarily starts its own HTTP server on port 80. The nginx proxy must not be running.

```bash
# Ensure port 80 is free (proxy is not running yet)
certbot certonly --standalone \
  -d YOUR_DOMAIN \
  --email YOUR_EMAIL \
  --agree-tos \
  --non-interactive
```

Expected output ends with:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem
```

- [ ] **Step 5: Set up Certbot auto-renewal hook**

```bash
mkdir -p /etc/letsencrypt/renewal-hooks/post
cat > /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh << 'EOF'
#!/bin/bash
docker compose -f /opt/automana/deploy/docker-compose.prod.yml exec proxy nginx -s reload
EOF
chmod +x /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh
```

Verify the systemd timer is active:

```bash
systemctl status certbot.timer
```

Expected: `active (waiting)`.

- [ ] **Step 6: Start the full prod stack**

```bash
cd /opt/automana
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Wait ~30 seconds for all services to reach healthy state:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Expected: all services (postgres, redis, backend, proxy, celery-worker, celery-beat, flower, db-backup-prod) show `healthy`. Ollama is not listed (it's in the `gpu` profile).

- [ ] **Step 7: Smoke test the live site**

```bash
curl -fsSL https://YOUR_DOMAIN/health
```

Expected:
```json
{"status": "ok"}
```

```bash
curl -fsSL https://YOUR_DOMAIN/docs | head -5
```

Expected: HTML of the OpenAPI docs page.

- [ ] **Step 8: Test the full CI/CD pipeline**

From your local machine, make a trivial commit on `dev`, merge to `main`, and verify the deploy workflow runs:

```bash
git checkout dev
git commit --allow-empty -m "chore: test CI/CD pipeline"
git push origin dev
# Open a PR from dev → main in GitHub and merge it
# Watch GitHub Actions → Deploy workflow → deploy job
```

Expected: deploy job completes green, `curl https://YOUR_DOMAIN/health` returns `{"status": "ok"}`.

- [ ] **Step 9: Verify B2 backup (first run)**

Trigger a manual backup to confirm rclone is working:

```bash
docker compose -f deploy/docker-compose.prod.yml exec db-backup-prod \
  bash -c 'pg_dump -Fc -f /backups/manual_test.dump $PGDATABASE && \
    rclone copy /backups/manual_test.dump :b2:automana-backups/postgres/ \
      --b2-account "$B2_ACCOUNT_ID" --b2-key "$B2_APPLICATION_KEY" && \
    rclone ls :b2:automana-backups/postgres/ \
      --b2-account "$B2_ACCOUNT_ID" --b2-key "$B2_APPLICATION_KEY"'
```

Expected: `manual_test.dump` is listed in the output with a file size.

---

## Rollback procedure

If a deploy breaks prod:

```bash
# On the VPS
cd /opt/automana
git log --oneline -5          # find the last good commit hash
git checkout <good-hash>
docker compose -f deploy/docker-compose.prod.yml up -d --build
curl -fsSL https://YOUR_DOMAIN/health
```

To permanently revert, create a revert commit on `main` and push — the deploy workflow will run automatically.
