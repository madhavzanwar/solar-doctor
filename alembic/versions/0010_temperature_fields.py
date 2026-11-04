"""detections radiometric temperature columns (max/ref temp, ΔT)

Revision ID: 0010
Revises: 0009

Nullable: images without a `_temp.raw` companion carry no temperatures.
Idempotent because `axalon.db.migrate.run_migrations` adds the same columns on
app startup — whichever runs first wins, the other is a no-op.
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

_COLUMNS = (
    'min_temp',
    'max_temp',
    'avg_temp',
    'reference_temp',
    'delta_t_measured',
    'delta_t_normalized',
)


def _existing_columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('detections')}


def upgrade() -> None:
    existing = _existing_columns()
    for name in _COLUMNS:
        if name not in existing:
            op.add_column('detections', sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    existing = _existing_columns()
    for name in reversed(_COLUMNS):
        if name in existing:
            op.drop_column('detections', name)
