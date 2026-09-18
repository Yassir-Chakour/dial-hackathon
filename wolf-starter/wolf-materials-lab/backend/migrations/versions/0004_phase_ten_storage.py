"""Phase Ten private object-storage metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_phase_ten_storage"
down_revision = "0003_phase_six_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("source_files")}
    if "object_key" not in existing:
        op.add_column("source_files", sa.Column("object_key", sa.String(length=512), nullable=True))
    if "encryption_key_ref" not in existing:
        op.add_column("source_files", sa.Column("encryption_key_ref", sa.String(length=256), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("source_files")}
    if "encryption_key_ref" in existing:
        op.drop_column("source_files", "encryption_key_ref")
    if "object_key" in existing:
        op.drop_column("source_files", "object_key")
