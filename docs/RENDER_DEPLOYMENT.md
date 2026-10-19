# Deploy DevGuard on Render

This guide prepares a separate Render API, Render Static Site, and Render PostgreSQL database. It does not change the existing Cloudflare Worker/D1 deployment. No Render service or hostname has been created by this repository change.

## What the code runs

- The backend is a FastAPI application using SQLAlchemy and Alembic. Render's PostgreSQL URLs (`postgres://` or `postgresql://`) are normalized to the installed `psycopg` 3 driver.
- The Docker image uses Python 3.12 and runs the PostgreSQL migrations before Uvicorn. PostgreSQL advisory locking serializes migration runs if instances start together. Current migrations create tables/indexes and add session revocation storage; they do not drop tables. Keep future schema changes backward-compatible during rolling deploys.
- The frontend is a Vite static SPA. It publishes `frontend/dist`; it does not need a running Node.js server or Nginx. Its build fails until `VITE_API_URL` is explicitly set to `/` or a public HTTPS API origin.
- There is no bundled/downloaded local ML model, model file, GPU dependency, or inference service. CI diagnosis always has deterministic rules. If `OPENAI_API_KEY` is configured, log excerpts (up to 12,000 characters in the AI request) are sent to OpenAI Chat Completions using `OPENAI_MODEL`; provider errors fall back to the deterministic result, which is labeled with `source: deterministic`. Without the key, AI enrichment is unavailable but deterministic diagnosis remains functional. Set the key only after reviewing log privacy and provider costs.

## 1. Create the Render Static Site to learn its origin

The frontend and backend origins must be exact values in the two services' configuration. Render assigns the Static Site URL during service creation. Create it first; its initial build will fail with a clear missing-`VITE_API_URL` message until the backend exists.

In Render, create a **Static Site** from `thrilokchaitanya-design/DevGuard`:

| Setting | Value |
| --- | --- |
| Branch | `main` |
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |
| Environment | `VITE_API_URL` — add after creating the backend, using its actual HTTPS public URL |
| Optional environment | `VITE_SITE_URL` — the actual HTTPS frontend origin, if sitemap generation should be enabled |

Copy the Static Site's actual `https://…onrender.com` URL from its dashboard. Do not use an internal hostname in browser configuration. After the frontend exists, configure the backend `ALLOWED_ORIGINS` to that exact origin with no trailing slash. For client-side routing, add a Static Site rewrite: source `/*`, destination `/index.html`, action **Rewrite**. The dashboard can also add security response headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).

## 2. Create PostgreSQL

In Render, create a PostgreSQL database in the same region as the API. Use its **Internal Database URL** for the backend service's `DATABASE_URL`; do not paste a database URL into Git or frontend settings. The app will apply Alembic migrations on startup under a PostgreSQL advisory lock. `/api/ready` checks database connectivity and returns 503 when the database cannot be reached.

Use a paid database for persistent production data. Render's current Free PostgreSQL option is limited to 1 GB, has no backups, and expires 30 days after creation; its post-expiration grace period is 14 days before deletion. Free web services spin down after 15 minutes idle, can take about a minute to wake, and use an ephemeral filesystem. DevGuard's records belong in PostgreSQL, never the backend container filesystem. See Render's [free service limitations](https://render.com/docs/free).

## 3. Create the backend Web Service

Create a **Web Service** from the same repository and branch:

| Setting | Value |
| --- | --- |
| Runtime | Docker |
| Root Directory | `backend` |
| Dockerfile Path | `./Dockerfile` |
| Docker Build Context Directory | `.` (the backend root) |
| Health Check Path | `/api/ready` |
| Build Command | Render builds `backend/Dockerfile`; it installs `backend/requirements.txt` |
| Start Command | Leave the Docker Command override empty. The image runs `sh -c 'python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers'`. |

Set these backend environment variables in Render:

**Required**

- `APP_ENV=production`
- `AUTH_MODE=demo`
- `DATABASE_URL` — the database's Internal Database URL
- `ALLOWED_ORIGINS` — the exact Static Site origin copied in step 1, without a trailing slash
- `SESSION_SECRET` — newly generated random secret, at least 32 characters
- `DEMO_ACCESS_PASSWORD` — newly chosen shared passphrase, at least 14 characters
- `SESSION_COOKIE_SAMESITE` — use `strict` when frontend and API are same-site; use `none` only if they are cross-site and you accept the browser's third-party-cookie restrictions. `None` is sent with `Secure`; exact CORS origin checks and CSRF token checks remain enabled.

**Optional integrations**

- `OPENAI_API_KEY` and optionally `OPENAI_MODEL` (default `gpt-4o-mini`)
- `GITHUB_WEBHOOK_SECRET` (only if configuring the signed `workflow_run` webhook)
- `SESSION_TTL_SECONDS` (default `28800`)
- `LOG_RETENTION_DAYS` (default `30`)

Do not set `PORT` manually. Render supplies it. The container binds Uvicorn to `0.0.0.0:$PORT` (with local fallback `8000`) and the Docker health check uses the same value. Render's default web service port is currently `10000`; use the injected variable rather than hardcoding that value. See [Render port binding](https://render.com/docs/web-services#port-binding).

Once the API service is created, copy its actual public HTTPS URL (not its private network hostname) into the Static Site's `VITE_API_URL`. The value must be an origin only, for example `https://<your-api-service>.onrender.com` with your real service host substituted. Save the environment and trigger a new frontend deploy. Then verify the deployed frontend origin matches backend `ALLOWED_ORIGINS`; update and redeploy the backend if needed.

## 4. Session cookies and CORS

The API uses credentialed CORS with an exact origin allowlist. Login returns a CSRF token in JSON; the frontend keeps it in memory and sends it on mutation requests, which lets the same code work when the API is on a separate origin. The API sets a host-only session cookie and a readable CSRF cookie, both `Secure` in production.

When frontend and API are separate origins under your own domain, put them on the same site (for example, sibling subdomains) and keep `SESSION_COOKIE_SAMESITE=strict`. If using cross-site service domains, `SESSION_COOKIE_SAMESITE=none` may be necessary, but browser privacy controls can block third-party cookies. If login succeeds but `/api/auth/session` reports unauthenticated, use a same-site custom domain or keep the frontend on the existing Cloudflare same-origin Worker deployment.

## 5. Keep the frontend on Cloudflare instead

The existing Cloudflare Worker serves the UI and API at one origin with D1. To keep that architecture, do not create a Render Static Site; continue using the Cloudflare instructions in [backend/cloudflare/README.md](../backend/cloudflare/README.md). Build the frontend with `VITE_API_URL=/`. The Render backend can still be deployed independently, but Cloudflare Worker CORS and cookies must be deliberately configured before pointing that frontend at a separate Render API. Same-origin Cloudflare currently avoids cross-site session-cookie restrictions.

## 6. Verify after deployment

Use the actual API service URL from Render:

1. Open `https://<actual-api-host>/api/health`; expect HTTP 200 and `{"status":"ok",...}`.
2. Open `https://<actual-api-host>/api/ready`; expect HTTP 200 and a reachable database.
3. Open the deployed Static Site and sign in with the Render `DEMO_ACCESS_PASSWORD`.
4. Confirm the dashboard says the API is connected, then load overview, issues, and workflows.
5. Submit a sample log. Without an OpenAI key, confirm diagnosis reports `source: deterministic`. With a key, check `source: ai` when the provider responds; provider failures are labeled deterministic rather than reported as AI success.
6. Run Spec Detective with a sample OpenAPI response. Check the browser Network panel for successful `/api/*` requests and credentialed CORS; never copy secrets into the frontend.
7. If auth fails, inspect sanitized Render service logs, confirm the exact Static Site origin in `ALLOWED_ORIGINS`, confirm `VITE_API_URL` uses the actual HTTPS API origin, and check cookie policy in browser devtools.

Health/readiness and deploy checks do not prove the public app is deployed until these steps are run against the actual Render URLs. Render service plans, database persistence, and backup availability affect uptime and data recovery; free services are suitable for evaluation, not production use. See Render's [free plan documentation](https://render.com/docs/free) and [deployment migration guidance](https://render.com/docs/deploys#pre-deploy-command).
