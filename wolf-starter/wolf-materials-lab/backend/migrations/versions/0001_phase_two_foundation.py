"""Phase Two persistence foundation."""
from alembic import op

revision = "0001_phase_two_foundation"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    from app.db.base import Base
    Base.metadata.create_all(op.get_bind())

def downgrade() -> None:
    from app.db.base import Base
    Base.metadata.drop_all(op.get_bind())
