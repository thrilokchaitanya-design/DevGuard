import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select, func
from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base, engine, get_db
from app.models import DiagnosticIssue, ErrorFingerprint, WorkflowRun
from app.schemas import AnalyzeRequest, IssueUpdate, SpecRequest
from app.services.diagnostics import DiagnosticService, enrich_with_ai
from app.services.spec_detective import SpecDetective
import app.models  # register ORM tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="DevGuard API", version="1.0.0", description="Deterministic first CI diagnostics and API contract drift detection.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Content-Type", "X-GitHub-Event", "X-Hub-Signature-256", "X-GitHub-Delivery"])

@app.get("/api/health")
def health(): return {"status": "ok", "service": "devguard-api"}

def issue_view(issue: DiagnosticIssue) -> dict:
    fp = issue.fingerprint
    return {"id": issue.id, "title": issue.title, "status": issue.status, "severity": issue.severity,
            "repository": issue.repository, "branch": issue.branch, "occurrences": fp.occurrences,
            "fingerprint": fp.hash[:12], "sample_log": fp.sample_log,
            "ai_summary": issue.ai_summary, "diagnosis": issue.ai_metadata,
            "created_at": (issue.created_at if issue.created_at.tzinfo else issue.created_at.replace(tzinfo=timezone.utc)).isoformat(), "updated_at": (issue.updated_at if issue.updated_at.tzinfo else issue.updated_at.replace(tzinfo=timezone.utc)).isoformat()}

@app.get("/api/overview")
def overview(db: Session = Depends(get_db)):
    issues = db.scalars(select(DiagnosticIssue).order_by(desc(DiagnosticIssue.updated_at)).limit(8)).all()
    total = db.scalar(select(func.count()).select_from(DiagnosticIssue)) or 0
    active = db.scalar(select(func.count()).select_from(DiagnosticIssue).where(DiagnosticIssue.status != "resolved")) or 0
    resolved = db.scalar(select(func.count()).select_from(DiagnosticIssue).where(DiagnosticIssue.status == "resolved")) or 0
    failures = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.conclusion == "failure")) or 0
    successes = db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.conclusion == "success")) or 0
    runs = db.scalar(select(func.count()).select_from(WorkflowRun)) or 0
    return {"active_issues": active, "total_issues": total, "resolved_issues": resolved, "workflow_runs": runs, "failed_runs": failures, "successful_runs": successes, "success_rate": round(successes*100/runs, 1) if runs else None, "recent_issues": [issue_view(x) for x in issues]}

@app.get("/api/issues")
def list_issues(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    if status and status not in {"open", "investigating", "resolved"}: raise HTTPException(422, "Invalid status filter")
    query = select(DiagnosticIssue).order_by(desc(DiagnosticIssue.updated_at)).limit(min(max(limit, 1), 100))
    if status: query = query.where(DiagnosticIssue.status == status)
    return [issue_view(x) for x in db.scalars(query).all()]

@app.patch("/api/issues/{issue_id}")
def update_issue(issue_id: int, body: IssueUpdate, db: Session = Depends(get_db)):
    issue = db.get(DiagnosticIssue, issue_id)
    if not issue: raise HTTPException(404, "Issue not found")
    issue.status = body.status
    issue.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(issue)
    return issue_view(issue)

@app.post("/api/diagnostics/analyze")
async def analyze(body: AnalyzeRequest, db: Session = Depends(get_db)):
    normalized = DiagnosticService.normalize_log(body.logs)
    fingerprint_hash = DiagnosticService.fingerprint(normalized)
    fp = db.scalar(select(ErrorFingerprint).where(ErrorFingerprint.hash == fingerprint_hash))
    now = datetime.now(timezone.utc)
    if not fp:
        fp = ErrorFingerprint(hash=fingerprint_hash, sample_log=normalized[:4000], occurrences=0, first_seen=now, last_seen=now)
        db.add(fp); db.flush()
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
    db.commit(); db.refresh(issue)
    return {"issue": issue_view(issue), "diagnosis": diagnosis, "normalized_log": normalized, "fingerprint": fingerprint_hash}

@app.post("/api/spec/validate")
def validate_spec(body: SpecRequest):
    findings = SpecDetective(body.spec).validate_actual_response(body.path, body.method, body.status_code, body.payload)
    return {"ok": not findings, "path": body.path, "method": body.method.upper(), "status_code": body.status_code, "findings": findings}

@app.get("/api/workflows")
def workflows(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.scalars(select(WorkflowRun).order_by(desc(WorkflowRun.created_at)).limit(min(max(limit, 1), 100))).all()
    return [{"id": r.id, "repository": r.repository, "workflow": r.workflow, "branch": r.branch, "conclusion": r.conclusion, "html_url": r.html_url, "created_at": r.created_at.isoformat()} for r in runs]

@app.post("/api/issues/{issue_id}/pr-comment")
def pr_comment(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(DiagnosticIssue, issue_id)
    if not issue: raise HTTPException(404, "Issue not found")
    d = issue.ai_metadata or {}
    return {"markdown": f"## DevGuard CI diagnosis\n\n**{issue.title}** ({issue.severity})\n\n{d.get('likely_cause', 'Review the attached CI logs for context.')}\n\n**Suggested next step:** {d.get('suggested_fix', 'Inspect the failed workflow step and rerun after the fix.')}\n\nFingerprint `{issue.fingerprint.hash[:12]}` · {issue.fingerprint.occurrences} occurrence(s).\n\n<sub>Diagnosis source: {d.get('source', 'deterministic')}. Please verify against the full CI logs.</sub>"}

@app.post("/api/webhooks/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 1_000_000: raise HTTPException(413, "Webhook payload too large")
    secret = settings.github_webhook_secret
    if not secret: raise HTTPException(503, "GitHub webhook secret is not configured")
    supplied = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected): raise HTTPException(401, "Invalid webhook signature")
    event = request.headers.get("X-GitHub-Event", "")
    if event != "workflow_run": return {"accepted": True, "ignored_event": event}
    payload = await request.json()
    run = payload.get("workflow_run", {})
    repo = payload.get("repository", {})
    if run.get("status") != "completed": return {"accepted": True, "ignored": "workflow is not completed"}
    run_id = str(run.get("id", ""))
    if not run_id: raise HTTPException(422, "workflow_run.id is required")
    existing = db.scalar(select(WorkflowRun).where(WorkflowRun.github_run_id == run_id))
    fields = {"repository": repo.get("full_name", "unknown"), "workflow": run.get("name", "workflow"), "branch": run.get("head_branch", "unknown"), "conclusion": run.get("conclusion", "unknown"), "html_url": run.get("html_url", "")}
    if existing:
        for k,v in fields.items(): setattr(existing, k, v)
    else: db.add(WorkflowRun(github_run_id=run_id, **fields))
    db.commit()
    return {"accepted": True, "run_id": run_id, "conclusion": fields["conclusion"]}


