"""Phase Four reconciliation snapshots, materialized records and issues."""

from alembic import op

revision = "0002_phase_four_reconciliation"
down_revision = "0001_phase_two_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The project uses SQLite for local development.  Metadata-driven creation
    # preserves the Phase Two migration's portability while adding only tables
    # absent from an already-initialized database.
    from app.db.base import Base
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    # Reconciliation history is intentionally not destructive.  Remove these
    # tables only through an explicit administrative migration if ever needed.
    pass

