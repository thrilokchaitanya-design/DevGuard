"""Add delivery deduplication and repository issue index.

Revision ID: 0002_webhook_deliveries
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_webhook_deliveries"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_diagnostic_issues_repository", "diagnostic_issues", ["repository"])
    op.create_table("webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.String(80), nullable=False),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("delivery_id", name="uq_webhook_deliveries_delivery_id"))
    op.create_index("ix_webhook_deliveries_delivery_id", "webhook_deliveries", ["delivery_id"], unique=True)

def downgrade():
    op.drop_index("ix_webhook_deliveries_delivery_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_diagnostic_issues_repository", table_name="diagnostic_issues")
