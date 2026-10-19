# DevGuard

DevGuard is a reliability workspace for diagnosing CI failures and checking captured API responses against OpenAPI contracts. The public demo runs on Cloudflare Workers with D1 storage; the application is also self-hostable.

## Deployment status

- The public demo is hosted on Cloudflare Workers with Cloudflare D1.
- Render deployment instructions are prepared in [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md), but no Render services have been created or deployed. A real Render API URL and frontend origin must be entered in the Render environment settings before production builds and login can work.
- To run locally, start the backend and frontend in two terminals using [Run DevGuard locally](#local-development), or use [Docker Compose](#docker-compose).

## What it does

### CI Doctor

- Accepts submitted workflow log text and repository, branch, and step labels.
- Normalizes volatile timestamps, numeric timestamps, UUIDs, memory addresses, and temporary paths before computing a stable SHA-256 fingerprint.
- Runs deterministic rules for assertion failures, missing Python/Node dependencies, timeouts, refused connections, permission errors, and memory exhaustion.
- Returns a summary, likely cause, suggested next step, confidence, severity, flaky-signal hint, and matching evidence from the log.
- Optionally enriches the deterministic result using the OpenAI Chat Completions API when an API key is configured. Without a key, the deterministic analyzer works on its own.
- Groups repeated fingerprints, counts occurrences, and creates or updates repository issues. Issues can be searched in the workspace and moved through open, investigating, and resolved states.

### Spec Detective

- Accepts an OpenAPI 3.x JSON document and a captured response path, method, status, and JSON payload.
- Matches concrete paths to templated OpenAPI paths, checks whether the operation and response status are documented, and validates JSON payloads against response schemas.
- Supports local component references and JSON Schema formats; rejects external references to prevent network fetches.
- Returns bounded, actionable findings without exposing internal exception details.

### GitHub workflow events

- Accepts GitHub `workflow_run` webhook deliveries, verifies the raw request body using `X-Hub-Signature-256`, and rejects invalid signatures.
- Deduplicates GitHub delivery IDs and upserts completed workflow summaries. The dashboard derives workflow totals and success rates from observed records.
- Generates copyable pull-request comment Markdown for an issue.
- Does not install a GitHub App, fetch workflow logs, authorize individual repositories, or publish comments automatically. GitHub workflow events do not contain full job logs; submit logs separately to CI Doctor.

### Workspace and public website

- Dashboard panels display API connection state and persisted issue/workflow data rather than fabricated metrics. Empty values remain empty until data arrives.
- Includes About, Documentation, Privacy, Terms, Contact/profile links, sign-in, and not-found/error states.
- The demo sign-in is one shared passphrase protecting one shared workspace. It is not OAuth, individual accounts, or per-user data isolation. Local development uses loopback-only access.
- Privacy and terms pages are project drafts, not legal advice or a claim of regulatory compliance.

## Requirements

- Python 3.10 or newer (Docker uses Python 3.12).
- Node.js 20 or newer (Docker uses Node.js 22).
- Docker Compose v2 only for the container stack.

## Local development

From the project root, create/activate an environment and install the backend dependencies:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

For an existing repository-level `.venv`, activate that environment instead. The backend defaults to loopback-only local access and SQLite at `backend/devguard.db`. Startup checks database reachability and performs retention cleanup. API docs are available at `http://127.0.0.1:8000/docs` while the server runs.

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Set `VITE_API_URL` in a frontend `.env.local` only when the API is at another address. Keep the API CORS allowlist in `ALLOWED_ORIGINS` aligned with the browser origin.

### Existing local SQLite database

Local development creates missing tables without dropping existing data. If the database predates Alembic, make a backup first, then from `backend` run:

```powershell
alembic stamp 0001_initial
alembic upgrade head
```

For a fresh database, run `alembic upgrade head`. Container startup applies migrations before Uvicorn starts. PostgreSQL starts serialize that step with an advisory lock so simultaneous instances cannot run Alembic concurrently. Do not stamp an unknown schema without inspecting and backing it up.

## Docker Compose

Copy `.env.example` to `.env`. Generate strong secrets (hex values are URL-safe for the PostgreSQL URL), fill `POSTGRES_PASSWORD`, `SESSION_SECRET`, and `DEMO_ACCESS_PASSWORD`, then run:

```powershell
docker compose up --build
```

Generate example random values with PowerShell:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

The frontend is at `http://localhost:8080`; Nginx forwards same-origin `/api/*` requests to the backend service inside Compose. For direct host access, the backend is at `http://localhost:8001` (container port 8000). Both host ports bind to loopback. PostgreSQL data is stored in the `pgdata` volume. This is a local container example; the public demo runs separately on Cloudflare Workers and D1.

## Configuration

Backend settings are read from environment variables or `backend/.env`:

| Setting | Purpose |
| --- | --- |
| `APP_ENV` | `development` locally; set `production` to enforce deployment checks and secure cookies. |
| `AUTH_MODE` | `local` for loopback-only development; `demo` for a shared passphrase workspace. |
| `DATABASE_URL` | SQLite locally or PostgreSQL with the `psycopg` driver. |
| `ALLOWED_ORIGINS` | Comma-separated exact frontend origins; production requires HTTPS origins. |
| `SESSION_SECRET` | Signs the demo session cookie. Production requires 32+ characters. |
| `DEMO_ACCESS_PASSWORD` | Shared demo passphrase. Production requires 14+ characters; provide it through a secret manager. |
| `SESSION_COOKIE_SAMESITE` | `strict` by default; set `none` only when a cross-site frontend must send API cookies. `None` requires HTTPS secure cookies and exact CORS/CSRF configuration. |
| `SESSION_TTL_SECONDS` | Signed session lifetime (default 28,800 seconds). |
| `GITHUB_WEBHOOK_SECRET` | Shared HMAC secret for GitHub webhook verification. |
| `OPENAI_API_KEY` | Optional key; submitted log excerpts are sent to OpenAI when enabled and may incur usage charges. |
| `OPENAI_MODEL` | Optional model name (default `gpt-4o-mini`). |
| `LOG_RETENTION_DAYS` | Age after which stored sample evidence is scrubbed (default 30 days). |

Frontend build settings: production requires `VITE_API_URL`. Use `/` for the same-origin Cloudflare Worker or Nginx proxy, or a verified public HTTPS API origin for a separate backend; the build rejects missing, local, insecure, and non-origin values. Local Vite development uses `http://localhost:8000` unless `VITE_API_URL` is explicitly set. `VITE_*` settings are public and must not contain secrets. Set `VITE_SITE_URL` only to the actual HTTPS public site origin to generate an indexable sitemap; unset/invalid values produce a disallow-all robots policy. `VITE_PUBLIC_CONTACT_EMAIL` is optional; no email address is assumed.

The Cloudflare demo uses a shared operator-managed passphrase and Cloudflare D1. Access the live site at https://devguard.thrilokchaitanya.workers.dev. Demo access is shared and is not suitable for private customer logs. Optional OpenAI analysis and GitHub webhook ingestion require operator-provided secrets. For Cloudflare deployment details, D1 migrations, and secret configuration, see [backend/cloudflare/README.md](backend/cloudflare/README.md). For self-hosted production, use a secret manager, secure and back up PostgreSQL, and validate the legal/privacy drafts before accepting real user data.

For a separate Render API + static frontend + managed PostgreSQL deployment, follow [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md). The Render backend URL must be created in your account before setting the frontend build variable; this repository does not assume or publish a Render service hostname.

## API

The following routes are available. Except health/readiness and the GitHub webhook, `/api/*` workspace routes require loopback access in local mode or a valid demo session in demo mode. Mutating demo requests require the session CSRF token and an allowlisted `Origin`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check. |
| `GET` | `/api/ready` | Database readiness check. |
| `POST` | `/api/auth/login` | Sign in to shared demo mode; sets HTTP-only signed session and CSRF cookies. |
| `GET` | `/api/auth/session` | Read session state. |
| `POST` | `/api/auth/logout` | Revoke the server-side session and clear cookies. |
| `GET` | `/api/overview` | Issue and observed workflow counters plus recent issues. |
| `GET` | `/api/issues` | List issues; supports `status` and bounded `limit` filters. |
| `PATCH` | `/api/issues/{id}` | Change issue status. |
| `POST` | `/api/diagnostics/analyze` | Fingerprint and diagnose submitted log text. |
| `POST` | `/api/spec/validate` | Validate a captured response against OpenAPI. |
| `GET` | `/api/workflows` | List recent observed workflow summaries. |
| `POST` | `/api/issues/{id}/pr-comment` | Return copyable comment Markdown. |
| `POST` | `/api/webhooks/github` | Verify and record signed `workflow_run` events. |

## Verification

```powershell
# Backend, from backend/
ruff check --select E4,E7,E9,F app tests
python -m pytest -q

# Frontend, from frontend/
npm test
npm run lint
npm run build
```

GitHub Actions runs the Alembic migration, Ruff checks, backend tests, frontend tests, ESLint, and production build for pull requests and pushes to `main`. Dependabot checks Python, npm, Docker images, and GitHub Actions weekly. The backend suite covers health/readiness, auth and revocation, CSRF rejection, deterministic diagnosis, issue grouping/status/comment generation, OpenAPI validation/external-reference rejection, webhook signatures/idempotency, and fingerprint normalization. The frontend suite covers the public landing and documentation routes.

## Security reporting

Report vulnerabilities through [GitHub Security Advisories](https://github.com/thrilokchaitanya-design/DevGuard/security/advisories/new). Do not include real secrets or private CI logs in public issues. Production uses should be reviewed and deployed by the operator; the repository does not claim a certification or security audit.
