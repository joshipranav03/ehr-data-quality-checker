# Deployment guide

The app is a single stateless FastAPI service — no database, no background
workers, no persistent storage. That makes it cheap and simple to deploy
anywhere that runs a container or a Python process.

---

## Contents
- [Local (development)](#local-development)
- [Docker](#docker)
- [Docker Compose](#docker-compose)
- [Production process model](#production-process-model)
- [Cloud platforms](#cloud-platforms)
- [Configuration](#configuration)
- [Health checks & observability](#health-checks--observability)
- [Scaling](#scaling)
- [Security hardening](#security-hardening)
- [Handling real PHI](#handling-real-phi)

---

## Local (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # auto-reloads on code changes
```

`--reload` is for development only — never run it in production.

---

## Docker

The included [`Dockerfile`](../Dockerfile) builds a slim, **non-root** image with
a built-in health check.

```bash
docker build -t ehr-data-quality-checker .
docker run -p 8000:8000 ehr-data-quality-checker
# → http://localhost:8000
```

Override the port:

```bash
docker run -e PORT=9000 -p 9000:9000 ehr-data-quality-checker
```

Image notes:
- Dependencies are installed in their own layer so code changes don't trigger a
  full reinstall.
- The container runs as UID `10001` (`appuser`), not root.
- `HEALTHCHECK` polls `/api/health`, so orchestrators can detect readiness.

---

## Docker Compose

```bash
docker compose up --build      # foreground
docker compose up -d           # detached
docker compose logs -f         # tail logs
docker compose down            # stop
```

See [`docker-compose.yml`](../docker-compose.yml) to adjust ports or environment.

---

## Production process model

For a single container, the shell-form `CMD` runs one Uvicorn process, which is
fine for light traffic. For more throughput, run multiple workers behind the
ASGI server. Two common options:

**Uvicorn with workers:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Gunicorn + Uvicorn workers (robust process manager):**
```bash
pip install gunicorn
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 -b 0.0.0.0:8000 \
  --timeout 60 --graceful-timeout 30
```

Rule of thumb: `workers = 2 × CPU cores + 1`. Each worker loads pandas and the
sample data, so size memory accordingly (~150–250 MB per worker).

Put a reverse proxy (Nginx, Caddy, or your platform's load balancer) in front
for TLS termination, request-size limits, and gzip.

---

## Cloud platforms (one-click / per-platform)

Because it's a standard container exposing one HTTP port and reading `$PORT`, it
drops onto most PaaS targets with no code changes. Ready-made config files live
at the repo root; pick whichever platform fits.

**Free-tier reality (verified 2026):** Render and Google Cloud Run have genuine,
recurring free allowances. Fly.io and Heroku no longer have a true free tier
(pay-as-you-go; near-zero at demo traffic with scale-to-zero). Hugging Face
Spaces is free for CPU.

### Hugging Face Spaces — best for a public demo (free)
Free Docker hosting where the data/health-tech community already looks. Full
walkthrough: [`deploy/huggingface/SETUP.md`](../deploy/huggingface/SETUP.md). In
short: create a Docker Space, push the repo, and use
[`deploy/huggingface/README.md`](../deploy/huggingface/README.md) (with its
`app_port: 8000` frontmatter) as the Space's `README.md`.

### Render — free Docker web service
A [`render.yaml`](../render.yaml) Blueprint is included. Either click the
**Deploy to Render** button (see the project README) or: New → Blueprint → point
at your repo. Render injects `PORT=10000`; the container honours it. Health check
hits `/healthz`. Note: free instances spin down after 15 min idle (~1 min cold
start) and have ephemeral disk, so history stays off.

### Google Cloud Run — permanent always-free allowance
No config file needed — it builds the `Dockerfile` from source:

```bash
gcloud run deploy ehr-data-quality-checker \
  --source . --region us-central1 --port 8080 \
  --allow-unauthenticated --memory 512Mi --min-instances 0 --max-instances 3
```

Cloud Run injects `PORT=8080`; scales to zero when idle (no cost). 2M
requests/month free.

### Railway
[`railway.json`](../railway.json) is included (Dockerfile builder). Railway
injects `$PORT` automatically. New Project → Deploy from repo.

### Fly.io
[`fly.toml`](../fly.toml) is included and scales to zero. Fly does **not** inject
`$PORT`, so the file sets `PORT=8080` in `[env]` to match `internal_port`. Deploy
with `fly launch --no-deploy` (to adopt the existing toml) then `fly deploy`.

### Heroku — container stack
[`heroku.yml`](../heroku.yml) and [`app.json`](../app.json) are included.

```bash
heroku create YOUR_APP
heroku stack:set container -a YOUR_APP
git push heroku main
```

### AWS App Runner / ECS Fargate
Push the image (see *Publishing the image* below) to ECR and point the service
at it; container port 8000.

### Kubernetes
One `Deployment` + `Service`. Use `/healthz` for both liveness and readiness:

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
  initialDelaySeconds: 5
readinessProbe:
  httpGet: { path: /healthz, port: 8000 }
```

---

## Distributing the package and image

Beyond hosting a live instance, you can publish the project so others can install
it. The [`publish.yml`](../.github/workflows/publish.yml) workflow does both
automatically when you push a version tag (`git tag v1.0.0 && git push --tags`).

### PyPI (pip install)
The project is a standard installable package (`pyproject.toml`).

```bash
python -m build                 # builds sdist + wheel into dist/
twine check dist/*              # validate metadata
twine upload dist/*             # publish (or use Trusted Publishing in CI)
```

Then anyone can:

```bash
pip install ehr-data-quality-checker
ehr-dq check your_data.csv          # CLI
python -m uvicorn app.main:app      # the web app
```

The wheel bundles the dashboard's static assets. The bundled sample datasets
ship in the source distribution (sdist) and the repo, not the wheel — the CLI
works on your own files regardless.

### Container image (GHCR / Docker Hub)
The `publish.yml` workflow builds and pushes a multi-tag image to GitHub
Container Registry on each tag. To publish manually to Docker Hub:

```bash
docker build -t joshipranav03/ehr-data-quality-checker:1.0.0 .
docker push joshipranav03/ehr-data-quality-checker:1.0.0
```

Users then run it with one command:

```bash
docker run -p 8000:8000 ghcr.io/joshipranav03/ehr-data-quality-checker:latest
```

---

## Configuration

All configuration is via environment variables — no config files to mount.

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8000` | Port to bind |
| `EHR_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Reject larger uploads (HTTP 400) |
| `EHR_MAX_ROWS` | `500000` | Reject files with more data rows |
| `EHR_HISTORY` | `on` | Set to `off` on ephemeral hosts (Render/Fly/Cloud Run/Spaces) |
| `EHR_DB_PATH` | `var/reports.db` | SQLite file for report history (needs a persistent disk) |

Raise the limits for big batch files, or lower them to constrain memory on small
instances. On hosts without durable storage, set `EHR_HISTORY=off` (the included
platform configs already do this).

---

## Health checks & observability

- **Health endpoint:** `GET /api/health` returns `200` with version info. Wire it
  into your platform's health checks (the Docker image and compose file already do).
- **Logs:** Uvicorn logs to stdout/stderr — collect them with your platform's log
  driver. Set `--log-level info` (or `warning` for quieter prod logs).
- **Metrics:** the service is stateless; track it with standard HTTP metrics
  (latency, 4xx/5xx rate) at the proxy or platform layer. For app-level metrics,
  add `prometheus-fastapi-instrumentator` and mount `/metrics`.

---

## Scaling

The service is **stateless** — every request is self-contained and nothing is
written to disk — so it scales horizontally: run N identical replicas behind a
load balancer and add more under load. The only per-request cost is CPU/memory
to parse and validate the CSV in pandas, which is bounded by the upload limits
above. For very large files, prefer the **CLI** in a batch job over an HTTP
upload.

---

## Security hardening

- **Run as non-root** — the image already does (`appuser`, UID 10001).
- **Terminate TLS** at a proxy/load balancer; don't expose Uvicorn directly.
- **Cap request size** at the proxy in addition to `EHR_MAX_UPLOAD_BYTES`.
- **Restrict CORS** if you add browser clients on other origins (none is enabled
  by default — the dashboard is same-origin).
- **No persistence** — uploads are parsed in memory and never written to disk,
  which shrinks the attack surface and simplifies compliance.
- Keep dependencies patched; pin exact versions in a lockfile for production
  builds (`requirements.txt` uses lower bounds for portability).

---

## Handling real PHI

The bundled data is synthetic. Before processing **real** Electronic Health
Record data, treat it as regulated PHI:

- **Transport:** require HTTPS end to end; disable plaintext HTTP.
- **In memory only:** the app does not persist uploads — keep it that way. Don't
  add logging that echoes row contents (the API only ever returns small *samples*
  of offending rows; consider disabling even that for production PHI).
- **Network isolation:** deploy inside a private network/VPC, not on the public
  internet. Add authentication (e.g. an API gateway, OAuth proxy, or mTLS) — the
  app ships without auth by design, since the right mechanism is environment-specific.
- **Compliance:** for HIPAA, ensure your hosting has a Business Associate
  Agreement (BAA) and that audit logging meets your requirements.
- **Data minimisation:** validate the smallest necessary extract; strip direct
  identifiers you don't need to check.

These are deployment responsibilities, not application defaults — the app gives
you a stateless, no-persistence core to build those controls around.
