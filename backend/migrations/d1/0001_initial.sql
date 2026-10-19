CREATE TABLE IF NOT EXISTS error_fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL UNIQUE,
    sample_log TEXT NOT NULL,
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_error_fingerprints_hash ON error_fingerprints(hash);
CREATE INDEX IF NOT EXISTS ix_error_fingerprints_last_seen ON error_fingerprints(last_seen);

CREATE TABLE IF NOT EXISTS diagnostic_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    severity TEXT NOT NULL DEFAULT 'medium',
    fingerprint_id INTEGER NOT NULL REFERENCES error_fingerprints(id),
    repository TEXT NOT NULL DEFAULT 'local',
    branch TEXT NOT NULL DEFAULT 'unknown',
    ai_summary TEXT,
    ai_metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_diagnostic_issues_status ON diagnostic_issues(status);
CREATE INDEX IF NOT EXISTS ix_diagnostic_issues_fingerprint_id ON diagnostic_issues(fingerprint_id);
CREATE INDEX IF NOT EXISTS ix_diagnostic_issues_repository ON diagnostic_issues(repository);
CREATE INDEX IF NOT EXISTS ix_diagnostic_issues_updated_at ON diagnostic_issues(updated_at);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_run_id TEXT NOT NULL UNIQUE,
    repository TEXT NOT NULL,
    workflow TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'unknown',
    conclusion TEXT NOT NULL,
    html_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workflow_runs_github_run_id ON workflow_runs(github_run_id);
CREATE INDEX IF NOT EXISTS ix_workflow_runs_repository ON workflow_runs(repository);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires_at ON auth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id TEXT NOT NULL UNIQUE,
    event TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_delivery_id ON webhook_deliveries(delivery_id);
