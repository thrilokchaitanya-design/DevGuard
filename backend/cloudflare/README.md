# Cloudflare deployment

The production Worker serves the built Vite site and FastAPI routes from one origin. It stores issues, fingerprints, workflow runs, webhook deliveries, and sessions in D1. The local Uvicorn app and its SQLAlchemy database remain available for development.

## Local Worker development

From this directory, copy `.dev.vars.example` to `.dev.vars`, replace the development secrets, then run:

```powershell
uv sync --all-groups
npm --prefix ../../frontend run build
npx wrangler d1 migrations apply devguard-production --local
uv run pywrangler dev
```

The Worker runs at `http://localhost:8787`. `.dev.vars` is ignored by Git.

## Production deploy

Set `SESSION_SECRET` and `DEMO_ACCESS_PASSWORD` as Wrangler secrets. Set `OPENAI_API_KEY` and `GITHUB_WEBHOOK_SECRET` only when those integrations are configured. The production origin is listed in `wrangler.jsonc`.

```powershell
npx wrangler d1 migrations apply devguard-production --remote
$env:VITE_SITE_URL = "https://devguard.thrilokchaitanya.workers.dev"
$env:VITE_API_URL = "/"
npm --prefix ../../frontend run build
uv run pywrangler deploy
```

The deployed site and API share the same HTTPS origin, so the frontend uses relative `/api/...` requests. The login passphrase is shared demo access; do not use it for private or customer log data.
