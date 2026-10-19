import hashlib
import hmac
import json
import uuid

from app.config import settings, sqlalchemy_database_url
from app.services.diagnostics import DiagnosticService


def test_health_readiness_and_diagnostics_auth(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/ready").json()["database"] == "reachable"
    assert client.get("/api/overview").status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"password": "test-passphrase-012345"},
        headers={"Origin": "http://testserver"},
    )
    assert login.status_code == 200
    assert any("SameSite=strict" in cookie for cookie in login.headers.get_list("set-cookie"))
    csrf = login.json()["csrf_token"]
    assert client.get("/api/overview").json()["total_issues"] == 0

    no_csrf = client.post(
        "/api/diagnostics/analyze",
        json={"logs": "ModuleNotFoundError: No module named 'pydantic_settings'"},
        headers={"Origin": "http://testserver"},
    )
    assert no_csrf.status_code == 403
    response = client.post(
        "/api/diagnostics/analyze",
        json={"logs": "ModuleNotFoundError: No module named 'pydantic_settings'", "repository": "owner/repo", "branch": "main", "step_name": "API tests"},
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["diagnosis"]["summary"] == "A required Python module is missing"
    assert response.json()["issue"]["occurrences"] == 1


def test_render_postgres_urls_use_installed_psycopg_driver():
    assert sqlalchemy_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert sqlalchemy_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert sqlalchemy_database_url("sqlite:///./devguard.db") == "sqlite:///./devguard.db"


def test_cross_site_production_cookies_are_secure_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "session_cookie_samesite", "none")
    monkeypatch.setattr(settings, "allowed_origins", "https://frontend.example.com")
    login = client.post(
        "/api/auth/login",
        json={"password": "test-passphrase-012345"},
        headers={"Origin": "https://frontend.example.com"},
    )
    assert login.status_code == 200
    cookies = login.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("Secure" in cookie and "SameSite=none" in cookie for cookie in cookies)


def test_frontend_origin_gets_cors_headers_on_auth_errors(client):
    response = client.get("/api/overview", headers={"Origin": "http://localhost:8080"})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_issue_grouping_status_and_pr_comment(client):
    login = client.post("/api/auth/login", json={"password": "test-passphrase-012345"}, headers={"Origin": "http://testserver"})
    headers = {"Origin": "http://testserver", "X-CSRF-Token": login.json()["csrf_token"]}
    body = {"logs": "ModuleNotFoundError: No module named 'httpx'", "repository": "owner/repo", "branch": "main", "step_name": "tests"}
    first = client.post("/api/diagnostics/analyze", json=body, headers=headers).json()["issue"]
    second = client.post("/api/diagnostics/analyze", json=body, headers=headers).json()["issue"]
    assert second["id"] == first["id"]
    assert second["occurrences"] == 2
    comment = client.post(f"/api/issues/{first['id']}/pr-comment", headers=headers)
    assert comment.status_code == 200 and "DevGuard CI diagnosis" in comment.json()["markdown"]
    resolved = client.patch(f"/api/issues/{first['id']}", json={"status": "resolved"}, headers=headers)
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert client.get("/api/overview").json()["active_issues"] == 0


def test_login_rejects_bad_password_and_logout_revokes_session(client):
    wrong = client.post("/api/auth/login", json={"password": "incorrect"}, headers={"Origin": "http://testserver"})
    assert wrong.status_code == 401
    login = client.post("/api/auth/login", json={"password": "test-passphrase-012345"}, headers={"Origin": "http://testserver"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    assert client.post("/api/auth/logout", headers={"Origin": "http://testserver", "X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_spec_validation_and_external_ref_rejection(client):
    login = client.post("/api/auth/login", json={"password": "test-passphrase-012345"}, headers={"Origin": "http://testserver"})
    csrf = login.json()["csrf_token"]
    spec = {"openapi": "3.0.0", "paths": {"/users/{id}": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}}}}}}}}}
    headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf}
    good = client.post("/api/spec/validate", json={"spec": spec, "path": "/users/7", "method": "GET", "status_code": 200, "payload": {"id": 7}}, headers=headers)
    assert good.status_code == 200 and good.json()["ok"] is True
    spec["paths"]["/users/{id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": "https://example.com/schema.json"}
    unsafe = client.post("/api/spec/validate", json={"spec": spec, "path": "/users/7", "method": "GET", "status_code": 200, "payload": {"id": 7}}, headers=headers)
    assert unsafe.status_code == 200 and unsafe.json()["ok"] is False


def test_webhook_signature_and_delivery_idempotency(client, monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "webhook-test-secret")
    delivery = str(uuid.uuid4())
    payload = {"repository": {"full_name": "owner/repo"}, "workflow_run": {"id": 12345, "status": "completed", "name": "CI", "head_branch": "main", "conclusion": "failure", "html_url": "https://github.com/owner/repo/actions/runs/12345"}}
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"webhook-test-secret", raw, hashlib.sha256).hexdigest()
    headers = {"X-GitHub-Event": "workflow_run", "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": signature}
    assert client.post("/api/webhooks/github", content=raw, headers=headers).status_code == 200
    assert client.post("/api/webhooks/github", content=raw, headers=headers).json()["duplicate"] is True
    headers["X-Hub-Signature-256"] = "sha256=bad"
    assert client.post("/api/webhooks/github", content=raw, headers=headers).status_code == 401


def test_normalization_and_fingerprint_are_stable():
    first = DiagnosticService.normalize_log("2026-10-19T10:11:12Z run 1234567890 failed")
    second = DiagnosticService.normalize_log("2026-10-20T11:12:13Z run 9876543210 failed")
    assert first == second
    assert DiagnosticService.fingerprint(first) == DiagnosticService.fingerprint(second)
