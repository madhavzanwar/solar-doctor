"""deficit detector columns: plant_alerts scope/ids/baseline/evidence, plants PI thresholds, telemetry.curtailed

Revision ID: 0012
Revises: 0011

Additive. Idempotent like 0011: `create_all()` may already have created the columns, so each add is
guarded by a column check. batch_alter_table keeps SQLite working.
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

_FK = {'inverter_id': ('inverters', 'fk_plant_alerts_inverter_id'), 'string_id': ('strings', 'fk_plant_alerts_string_id')}

_COLUMNS = {
    'plant_alerts': [
        sa.Column('scope', sa.String(16), nullable=False, server_default='plant'),
        sa.Column('inverter_id', sa.Integer(), nullable=True),
        sa.Column('string_id', sa.Integer(), nullable=True),
        sa.Column('baseline', sa.String(16), nullable=True),
        sa.Column('evidence_json', sa.Text(), nullable=True),
    ],
    'plants': [
        sa.Column('pi_warning', sa.Float(), nullable=False, server_default='0.95'),
        sa.Column('pi_critical', sa.Float(), nullable=False, server_default='0.9'),
        sa.Column('deficit_min_clear_hours', sa.Integer(), nullable=False, server_default='3'),
    ],
    'telemetry': [sa.Column('curtailed', sa.Boolean(), nullable=True)],
}


def _have(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c['name'] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def upgrade() -> None:
    for table, cols in _COLUMNS.items():
        have = _have(table)
        todo = [c for c in cols if c.name not in have]
        if not todo or not have:
            continue
        with op.batch_alter_table(table) as batch:
            for c in todo:
                batch.add_column(c)
                if table == 'plant_alerts' and c.name in _FK:
                    ref, name = _FK[c.name]
                    batch.create_foreign_key(name, ref, [c.name], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    for table, cols in _COLUMNS.items():
        have = _have(table)
        names = [c.name for c in cols if c.name in have]
        if not names:
            continue
        with op.batch_alter_table(table) as batch:
            for n in names:
                if table == 'plant_alerts' and n in _FK:
                    batch.drop_constraint(_FK[n][1], type_='foreignkey')
                batch.drop_column(n)
