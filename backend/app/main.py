import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.auth import CSRF_COOKIE, SESSION_COOKIE, issue_session, login_limiter, read_session, session_cookie_samesite
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import AuthSession, DiagnosticIssue, ErrorFingerprint, WebhookDelivery, WorkflowRun
from app.schemas import AnalyzeRequest, IssueUpdate, LoginRequest, SpecRequest
from app.services.diagnostics import DiagnosticService, enrich_with_ai
from app.services.spec_detective import SpecDetective
import app.models

logger = logging.getLogger("devguard")
RATE_WINDOWS: dict[tuple[str, str], list[float]] = {}
MAX_REQUEST_BYTES = 2_000_000


def prune_expired_evidence() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, settings.log_retention_days))
    with SessionLocal() as db:
        fingerprints = db.scalars(select(ErrorFingerprint).where(ErrorFingerprint.last_seen < cutoff)).all()
        for fingerprint in fingerprints:
            fingerprint.sample_log = "[evidence expired by retention policy]"
        issues = db.scalars(select(DiagnosticIssue).where(DiagnosticIssue.created_at < cutoff)).all()
        for issue in issues:
            if issue.ai_metadata and issue.ai_metadata.get("evidence"):
                metadata = dict(issue.ai_metadata)
                metadata["evidence"] = "[evidence expired by retention policy]"
                issue.ai_metadata = metadata
        db.commit()


async def retention_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(prune_expired_evidence)
        except Exception:
            logger.exception("Evidence-retention cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_security_config()
    if settings.app_env.lower() != "production":
        Base.metadata.create_all(bind=engine)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    try:
        await asyncio.to_thread(prune_expired_evidence)
    except SQLAlchemyError:
        logger.exception("Startup evidence-retention cleanup failed")
    task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="DevGuard API", version="1.1.0", description="Deterministic-first CI diagnostics and API contract drift detection.", lifespan=lifespan)


@app.middleware("http")
async def request_security(request: Request, call_next):
    path = request.url.path
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > (1_000_000 if path == "/api/webhooks/github" else MAX_REQUEST_BYTES):
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
    ip = request.client.host if request.client else "unknown"
    if path == "/api/auth/login":
        now = time.monotonic()
        if not login_limiter.allow(ip, now):
            return JSONResponse({"detail": "Too many sign-in attempts. Try again later."}, status_code=429)
    elif path in {"/api/diagnostics/analyze", "/api/spec/validate"}:
        key = (path, ip)
        now = time.monotonic()
        hits = [stamp for stamp in RATE_WINDOWS.get(key, []) if stamp > now - 60]
        if len(hits) >= 30:
            return JSONResponse({"detail": "Request rate limit exceeded. Try again shortly."}, status_code=429)
        hits.append(now)
        RATE_WINDOWS[key] = hits
    if path.startswith("/api/") and path not in {"/api/health", "/api/ready", "/api/auth/login", "/api/auth/session", "/api/webhooks/github"}:
        if settings.auth_mode == "local":
            if ip not in {"127.0.0.1", "::1", "localhost", "testclient"}:
                return JSONResponse({"detail": "Local access is limited to this machine."}, status_code=403)
        else:
            session = read_session(request.cookies.get(SESSION_COOKIE))
            if not session or session.get("sub") != "shared-demo" or not _session_is_active(session):
                return JSONResponse({"detail": "Sign-in required."}, status_code=401)
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
                csrf_header = request.headers.get("X-CSRF-Token", "")
                if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header) or not secrets.compare_digest(str(session.get("csrf", "")), csrf_cookie):
                    return JSONResponse({"detail": "CSRF validation failed."}, status_code=403)
    if settings.auth_mode == "demo" and request.method in {"POST", "PUT", "PATCH", "DELETE"} and path != "/api/webhooks/github":
        origin = request.headers.get("origin", "").rstrip("/")
        if origin not in settings.cors_origins:
            return JSONResponse({"detail": "Request origin is not allowed."}, status_code=403)
    try:
        response = await call_next(request)
    except SQLAlchemyError:
        logger.exception("Database request failed")
        return JSONResponse({"detail": "Database request failed. Check database readiness and retry."}, status_code=503)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.app_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


# Keep CORS outside request_security so browser clients receive CORS headers
# on authentication, CSRF, and rate-limit errors as well as successful responses.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-CSRF-Token", "X-GitHub-Event", "X-Hub-Signature-256", "X-GitHub-Delivery"])


def _session_is_active(payload: dict) -> bool:
    session_id = payload.get("jti")
    if not session_id:
        return False
    with SessionLocal() as db:
        record = db.get(AuthSession, session_id)
        if not record or record.revoked_at:
            return False
        expiration = record.expires_at
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        return expiration > datetime.now(timezone.utc)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "devguard-api"}


@app.get("/api/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "reachable"}
    except SQLAlchemyError:
        raise HTTPException(503, "Database is unavailable")


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    now = time.monotonic()
    ip = request.client.host if request.client else "unknown"
    login_limiter.record(ip, now)
    if settings.auth_mode != "demo":
        raise HTTPException(404, "Demo sign-in is disabled in local mode")
    if not settings.demo_access_password:
        raise HTTPException(503, "Demo access is not configured")
    if not hmac.compare_digest(body.password.encode(), settings.demo_access_password.encode()):
        raise HTTPException(401, "Invalid sign-in details")
    token, csrf = issue_session()
    payload = read_session(token)
    if not payload or not payload.get("jti"):
        raise HTTPException(500, "Could not create a sign-in session")
    db.add(AuthSession(session_id=payload["jti"], expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)))
    db.commit()
    secure = settings.app_env.lower() == "production"
    samesite = session_cookie_samesite()
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_seconds, httponly=True, secure=secure, samesite=samesite, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=settings.session_ttl_seconds, httponly=False, secure=secure, samesite=samesite, path="/")
    return {"authenticated": True, "csrf_token": csrf, "mode": "shared-demo"}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    payload = read_session(request.cookies.get(SESSION_COOKIE))
    if payload and payload.get("jti"):
        record = db.get(AuthSession, payload["jti"])
        if record and not record.revoked_at:
            record.revoked_at = datetime.now(timezone.utc)
            db.commit()
    samesite = session_cookie_samesite()
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=settings.app_env.lower() == "production", samesite=samesite)
    response.delete_cookie(CSRF_COOKIE, path="/", httponly=False, secure=settings.app_env.lower() == "production", samesite=samesite)
    return {"authenticated": False}


@app.get("/api/auth/session")
def auth_session(request: Request):
    if settings.auth_mode == "local":
        ip = request.client.host if request.client else "unknown"
        if ip not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(403, "Local access is limited to this machine.")
        return {"authenticated": True, "mode": "local"}
    session = read_session(request.cookies.get(SESSION_COOKIE))
    if not session or session.get("sub") != "shared-demo" or not _session_is_active(session):
        return {"authenticated": False, "mode": "shared-demo"}
    return {"authenticated": True, "mode": "shared-demo", "csrf_token": session.get("csrf")}


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def issue_view(issue: DiagnosticIssue) -> dict:
    fp = issue.fingerprint
    return {"id": issue.id, "title": issue.title, "status": issue.status, "severity": issue.severity,
            "repository": issue.repository, "branch": issue.branch, "occurrences": fp.occurrences,
            "fingerprint": fp.hash[:12], "sample_log": fp.sample_log[:4000],
            "ai_summary": issue.ai_summary, "diagnosis": issue.ai_metadata,
            "created_at": _iso(issue.created_at), "updated_at": _iso(issue.updated_at)}


@app.get("/api/overview")
def overview(db: Session = Depends(get_db)):
    issues = db.scalars(select(DiagnosticIssue).order_by(desc(DiagnosticIssue.updated_at)).limit(8)).all()
    total = db.scalar(select(func.count()).select_from(DiagnosticIssue)) or 0
    active = db.scalar(select(func.count()).select_from(DiagnosticIssue).where(DiagnosticIssue.status != "resolved")) or 0
    resolved = db.scalar(select(func.count()).select_from(DiagnosticIssue).where(DiagnosticIssue.status == "resolved")) or 0
    failures = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.conclusion == "failure")) or 0
    successes = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.conclusion == "success")) or 0
    runs = db.scalar(select(func.count()).select_from(WorkflowRun)) or 0
    return {"active_issues": active, "total_issues": total, "resolved_issues": resolved, "workflow_runs": runs, "failed_runs": failures, "successful_runs": successes, "success_rate": round(successes * 100 / runs, 1) if runs else None, "recent_issues": [issue_view(x) for x in issues]}


@app.get("/api/issues")
def list_issues(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    if status and status not in {"open", "investigating", "resolved"}:
        raise HTTPException(422, "Invalid status filter")
    query = select(DiagnosticIssue).order_by(desc(DiagnosticIssue.updated_at)).limit(min(max(limit, 1), 100))
    if status:
        query = query.where(DiagnosticIssue.status == status)
    return [issue_view(issue) for issue in db.scalars(query).all()]


@app.patch("/api/issues/{issue_id}")
def update_issue(issue_id: int, body: IssueUpdate, db: Session = Depends(get_db)):
    issue = db.get(DiagnosticIssue, issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")
    transitions = {"open": {"open", "investigating", "resolved"}, "investigating": {"open", "investigating", "resolved"}, "resolved": {"open", "resolved"}}
    if body.status not in transitions[issue.status]:
        raise HTTPException(409, "Invalid issue status transition")
    issue.status = body.status
    issue.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(issue)
    return issue_view(issue)


@app.post("/api/diagnostics/analyze")
async def analyze(body: AnalyzeRequest, db: Session = Depends(get_db)):
    normalized = DiagnosticService.normalize_log(body.logs)
    fingerprint_hash = DiagnosticService.fingerprint(normalized)
    now = datetime.now(timezone.utc)
    fp = db.scalar(select(ErrorFingerprint).where(ErrorFingerprint.hash == fingerprint_hash))
    if not fp:
        fp = ErrorFingerprint(hash=fingerprint_hash, sample_log=normalized[:4000], occurrences=0, first_seen=now, last_seen=now)
        db.add(fp)
        db.flush()
    fp.occurrences += 1
    fp.last_seen = now
    diagnosis = DiagnosticService.diagnose(body.logs)
    diagnosis = await enrich_with_ai(body.logs, diagnosis, settings.openai_api_key, settings.openai_model)
    issue = db.scalar(select(DiagnosticIssue).where(DiagnosticIssue.fingerprint_id == fp.id, DiagnosticIssue.repository == body.repository, DiagnosticIssue.status != "resolved").order_by(desc(DiagnosticIssue.updated_at)))
    if issue is None:
        issue = DiagnosticIssue(title=f"{diagnosis['summary']} · {body.step_name}"[:240], severity=diagnosis["severity"], fingerprint=fp, repository=body.repository, branch=body.branch)
        db.add(issue)
    else:
        issue.branch = body.branch
        issue.severity = diagnosis["severity"]
    issue.ai_summary = diagnosis["summary"]
    issue.ai_metadata = diagnosis
    db.commit()
    db.refresh(issue)
    return {"issue": issue_view(issue), "diagnosis": diagnosis, "normalized_log": normalized, "fingerprint": fingerprint_hash}


@app.post("/api/spec/validate")
def validate_spec(body: SpecRequest):
    findings = SpecDetective(body.spec).validate_actual_response(body.path, body.method, body.status_code, body.payload)
    return {"ok": not findings, "path": body.path, "method": body.method.upper(), "status_code": body.status_code, "findings": findings}


@app.get("/api/workflows")
def workflows(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.scalars(select(WorkflowRun).order_by(desc(WorkflowRun.created_at)).limit(min(max(limit, 1), 100))).all()
    return [{"id": run.id, "repository": run.repository, "workflow": run.workflow, "branch": run.branch, "conclusion": run.conclusion, "html_url": run.html_url, "created_at": _iso(run.created_at)} for run in runs]


@app.post("/api/issues/{issue_id}/pr-comment")
def pr_comment(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(DiagnosticIssue, issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")
    diagnosis = issue.ai_metadata or {}
    markdown = f"## DevGuard CI diagnosis\n\n**{issue.title}** ({issue.severity})\n\n{diagnosis.get('likely_cause', 'Review the attached CI logs for context.')}\n\n**Suggested next step:** {diagnosis.get('suggested_fix', 'Inspect the failed workflow step and rerun after the fix.')}\n\nFingerprint `{issue.fingerprint.hash[:12]}` · {issue.fingerprint.occurrences} occurrence(s).\n\n<sub>Diagnosis source: {diagnosis.get('source', 'deterministic')}. Please verify against the full CI logs.</sub>"
    return {"markdown": markdown}


@app.post("/api/webhooks/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "Webhook payload too large")
    secret = settings.github_webhook_secret
    if not secret:
        raise HTTPException(503, "GitHub webhook secret is not configured")
    supplied = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid webhook signature")
    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if event != "workflow_run":
        return {"accepted": True, "ignored_event": event}
    try:
        uuid.UUID(delivery_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, "A valid X-GitHub-Delivery UUID is required")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON webhook payload")
    if not isinstance(payload, dict):
        raise HTTPException(422, "Webhook JSON must be an object")
    run = payload.get("workflow_run", {})
    repo = payload.get("repository", {})
    if not isinstance(run, dict) or not isinstance(repo, dict):
        raise HTTPException(422, "Invalid workflow_run payload")
    if run.get("status") != "completed":
        return {"accepted": True, "ignored": "workflow is not completed"}
    run_id = str(run.get("id", ""))
    if not run_id or len(run_id) > 80:
        raise HTTPException(422, "workflow_run.id is required")
    existing_delivery = db.scalar(select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id))
    if existing_delivery:
        return {"accepted": True, "duplicate": True, "delivery_id": delivery_id}
    try:
        db.add(WebhookDelivery(delivery_id=delivery_id, event=event))
        existing = db.scalar(select(WorkflowRun).where(WorkflowRun.github_run_id == run_id))
        fields = {"repository": str(repo.get("full_name", "unknown"))[:240], "workflow": str(run.get("name", "workflow"))[:240], "branch": str(run.get("head_branch", "unknown"))[:240], "conclusion": str(run.get("conclusion", "unknown"))[:32], "html_url": str(run.get("html_url", ""))[:2000]}
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(WorkflowRun(github_run_id=run_id, **fields))
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)):
            return {"accepted": True, "duplicate": True, "delivery_id": delivery_id}
        raise HTTPException(409, "Workflow event conflicts with an existing record")
    return {"accepted": True, "run_id": run_id, "conclusion": fields["conclusion"]}


