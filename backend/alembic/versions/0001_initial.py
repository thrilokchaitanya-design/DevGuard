"""Create initial DevGuard persistence tables.

Revision ID: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("error_fingerprints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("sample_log", sa.Text(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("hash", name="uq_error_fingerprints_hash"))
    op.create_index("ix_error_fingerprints_hash", "error_fingerprints", ["hash"], unique=True)
    op.create_table("diagnostic_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("fingerprint_id", sa.Integer(), sa.ForeignKey("error_fingerprints.id"), nullable=False),
        sa.Column("repository", sa.String(240), nullable=False),
        sa.Column("branch", sa.String(240), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_diagnostic_issues_fingerprint_id", "diagnostic_issues", ["fingerprint_id"])
    op.create_index("ix_diagnostic_issues_status", "diagnostic_issues", ["status"])
    op.create_table("workflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_run_id", sa.String(80), nullable=False),
        sa.Column("repository", sa.String(240), nullable=False),
        sa.Column("workflow", sa.String(240), nullable=False),
        sa.Column("branch", sa.String(240), nullable=False),
        sa.Column("conclusion", sa.String(32), nullable=False),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("github_run_id", name="uq_workflow_runs_github_run_id"))
    op.create_index("ix_workflow_runs_github_run_id", "workflow_runs", ["github_run_id"], unique=True)
    op.create_index("ix_workflow_runs_repository", "workflow_runs", ["repository"])

def downgrade():
    op.drop_index("ix_workflow_runs_repository", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_github_run_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_diagnostic_issues_status", table_name="diagnostic_issues")
    op.drop_index("ix_diagnostic_issues_fingerprint_id", table_name="diagnostic_issues")
    op.drop_table("diagnostic_issues")
    op.drop_index("ix_error_fingerprints_hash", table_name="error_fingerprints")
    op.drop_table("error_fingerprints")
