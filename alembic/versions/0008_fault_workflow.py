"""fault repair workflow: assignee/due date/priority/resolution on panel_faults + fault_photos

Revision ID: 0008
Revises: 0007

Idempotent on purpose: local SQLite DBs built by `Base.metadata.create_all` +
`axalon.db.migrate` may already carry these columns/tables before Alembic runs.
Existing rows are untouched — every new column is nullable and the status
column keeps its values (the new statuses are additive).
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

_NEW_COLUMNS = (
    ('assignee', sa.String(200)),
    ('due_date', sa.Date()),
    ('priority', sa.String(16)),
    ('resolved_at', sa.DateTime()),
    ('resolution_note', sa.Text()),
)


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    existing = {c['name'] for c in _inspector().get_columns('panel_faults')}
    missing = [(name, type_) for name, type_ in _NEW_COLUMNS if name not in existing]
    if missing:
        with op.batch_alter_table('panel_faults') as batch:
            for name, type_ in missing:
                batch.add_column(sa.Column(name, type_, nullable=True))

    if not _inspector().has_table('fault_photos'):
        op.create_table(
            'fault_photos',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('fault_id', sa.Integer(), sa.ForeignKey('panel_faults.id'), nullable=False),
            sa.Column('original_name', sa.String(200), nullable=False),
            sa.Column('stored_name', sa.String(400), nullable=False),
            sa.Column('content_type', sa.String(64), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_fault_photos_fault_id', 'fault_photos', ['fault_id'])


def downgrade() -> None:
    if _inspector().has_table('fault_photos'):
        op.drop_index('ix_fault_photos_fault_id', 'fault_photos')
        op.drop_table('fault_photos')
    existing = {c['name'] for c in _inspector().get_columns('panel_faults')}
    present = [name for name, _ in reversed(_NEW_COLUMNS) if name in existing]
    if present:
        with op.batch_alter_table('panel_faults') as batch:
            for name in present:
                batch.drop_column(name)
