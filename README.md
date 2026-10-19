# DevGuard

**CI diagnostics and API contract monitoring, deterministic first and AI enhanced second.** DevGuard groups recurring CI failures with stable fingerprints, explains common failure signatures, and checks observed API responses against OpenAPI 3.x contracts. It keeps working without an AI key; an optional OpenAI integration can add structured diagnosis to the rule-based result.

## Features

- Normalize timestamps, UUIDs, memory addresses, and temporary file paths before hashing logs with SHA-256.
- Detect common Python, Node, assertion, timeout, connection, permission, and memory failures with evidence and actionable next steps.
- Persist fingerprints, issue history, and workflow-run summaries in SQLite for local development or PostgreSQL in Docker.
- Validate endpoint and method coverage, response status codes, JSON Schema requirements, formats, and local OpenAPI component references.
- Verify GitHub webhook HMAC signatures and ingest completed `workflow_run` summaries.
- Track issue state and generate a ready-to-copy pull request comment.
- Responsive React dashboard backed by real API data. Empty metrics remain empty until events or analysis provide data.

## Run locally

Requires Python 3.10+ and Node.js 20+.

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend creates a local `devguard.db` SQLite database on first start. Interactive API docs are at `http://localhost:8000/docs`.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. To use the example configuration locally, copy `..\.env.example` to `backend\.env`. Configure a different frontend API base with `frontend/.env.local`:

```env
VITE_API_URL=http://localhost:8000
```

## Docker Compose

From the project root, copy `.env.example` to `.env`, set a strong `POSTGRES_PASSWORD`, then run:

```sh
docker compose up --build
```

The dashboard will be at `http://localhost:8080`; the API is at `http://localhost:8000`. The Compose setup includes a persistent PostgreSQL volume. The example database password is only for local development.

## GitHub Actions webhook

Configure `GITHUB_WEBHOOK_SECRET` on the backend and the same secret in your GitHub repository webhook settings. Set the payload URL to `https://YOUR_HOST/api/webhooks/github`, choose JSON content type, and subscribe to `workflow_run`. DevGuard verifies `X-Hub-Signature-256`, rejects missing or invalid signatures, and stores completed run summaries. GitHub does not include job logs in this event; submit the failure log through `POST /api/diagnostics/analyze` (or your own log collection flow) for fingerprinting and diagnosis.

## API quick reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/overview` | Real issue and workflow counters |
| `GET` | `/api/issues` | List tracked issues; optional `status` and `limit` |
| `PATCH` | `/api/issues/{id}` | Change issue status |
| `POST` | `/api/diagnostics/analyze` | Fingerprint logs and create/update diagnosis |
| `POST` | `/api/spec/validate` | Compare an observed response with an OpenAPI document |
| `GET` | `/api/workflows` | Recent GitHub workflow run summaries |
| `POST` | `/api/issues/{id}/pr-comment` | Generate Markdown for a PR comment |
| `POST` | `/api/webhooks/github` | Verify and ingest GitHub workflow events |

### Analyze a CI failure

```sh
curl -X POST http://localhost:8000/api/diagnostics/analyze \
  -H 'Content-Type: application/json' \
  -d '{"repository":"acme/api","branch":"main","step_name":"pytest","logs":"ModuleNotFoundError: No module named httpx"}'
```

### Validate a response

```json
{
  "spec": {
    "openapi": "3.1.0",
    "info": {"title": "Example", "version": "1"},
    "paths": {"/health": {"get": {"responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "required": ["status"], "properties": {"status": {"type": "string"}}}}}}}}}}
  },
  "path": "/health",
  "method": "GET",
  "status_code": 200,
  "payload": {"status": "ok"}
}
```

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./devguard.db` | SQLAlchemy URL; use PostgreSQL for shared deployments |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed browser origin |
| `GITHUB_WEBHOOK_SECRET` | empty | Required to enable signed webhook ingestion |
| `OPENAI_API_KEY` | empty | Optional; sent to OpenAI only when enabled |
| `OPENAI_MODEL` | `gpt-4o-mini` | Optional structured diagnosis model |
| `VITE_API_URL` | `http://localhost:8000` | Frontend API base URL at build time |

## Operational notes

This is an application foundation, not a claim that a hosted production deployment is already provisioned. Before exposing it publicly, configure TLS and a secret manager, restrict API access, add database migrations and backup/retention policies, and review AI data handling for your organization. The included GitHub webhook authenticates event origin; it does not implement GitHub App installation, repository authorization, log download, or automatic PR comment posting. The PR comment endpoint returns Markdown for a caller to post through an appropriately authorized GitHub integration.

