"""Phase Ten durable background job records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0005_phase_ten_jobs"
down_revision = "0004_phase_ten_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "job_records" in inspector.get_table_names():
        return
    op.create_table(
        "job_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_summary", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_job_tenant_idempotency"),
    )
    op.create_index("ix_job_records_status", "job_records", ["status"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "job_records" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("job_records")}
    if "ix_job_records_status" in indexes:
        op.drop_index("ix_job_records_status", table_name="job_records")
    op.drop_table("job_records")
