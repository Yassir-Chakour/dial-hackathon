"""Phase Six immutable decision snapshots, audit trail and mock actions."""

from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy import Boolean, Integer, String

revision = "0003_phase_six_decisions"
down_revision = "0002_phase_four_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    bind = op.get_bind()
    # 0001/0002 used metadata creation, so existing local databases may have
    # the original Phase Two columns. Add Phase Six columns explicitly before
    # creating the new immutable tables.
    additions = {
        "recommendations": {
            "input_snapshot_id": String(36), "result_hash": String(64), "input_hash": String(64),
            "recommendation_key_stable": String(256), "blocking_issue_ids_json": Base.metadata.tables["recommendations"].c.blocking_issue_ids_json.type,
            "evidence_complete": Boolean(), "version": Integer(), "parent_recommendation_id": String(36), "tenant_id": String(128),
        },
        "corrections": {
            "correction_hash": String(64), "validation_type": String(64), "evidence_json": Base.metadata.tables["corrections"].c.evidence_json.type,
            "status": String(32), "requires_reconciliation": Boolean(),
        },
        "approvals": {
            "result_hash": String(64), "input_snapshot_id": String(36), "input_hash": String(64),
            "policy_version": String(32), "request_id": String(128),
        },
    }
    inspector = inspect(bind)
    for table_name, columns in additions.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column_type in columns.items():
            if column_name not in existing:
                op.add_column(table_name, __import__("sqlalchemy").Column(column_name, column_type, nullable=True))
    op.execute(text("UPDATE recommendations SET result_hash = calculation_hash WHERE result_hash IS NULL OR result_hash = ''"))
    op.execute(text("UPDATE recommendations SET version = 1 WHERE version IS NULL"))
    op.execute(text("UPDATE corrections SET validation_type = 'schema' WHERE validation_type IS NULL"))
    op.execute(text("UPDATE corrections SET status = 'accepted' WHERE status IS NULL"))
    op.execute(text("UPDATE approvals SET policy_version = 'phase-six-v1' WHERE policy_version IS NULL"))
    Base.metadata.create_all(bind)


def downgrade() -> None:
    # Decision history is append-only and is not removed by a routine downgrade.
    pass
