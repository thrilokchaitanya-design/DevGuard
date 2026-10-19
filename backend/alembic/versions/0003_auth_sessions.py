"""Persist demo-session revocation state."""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "0003_auth_sessions"
down_revision = "0002_webhook_deliveries"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("auth_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

def downgrade():
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")
