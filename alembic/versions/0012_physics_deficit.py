"""deficit detector columns: plant_alerts scope/ids/baseline/evidence, plants PI thresholds, telemetry.curtailed, plant_analytics table

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
    if not sa.inspect(op.get_bind()).has_table('plant_analytics'):
        op.create_table(
            'plant_analytics',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('kind', sa.String(16), nullable=False),
            sa.Column('day', sa.Date(), nullable=False),
            sa.Column('method', sa.String(32), nullable=False),
            sa.Column('label', sa.String(16), nullable=False),
            sa.Column('result_json', sa.Text(), nullable=False),
            sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('plant_id', 'kind', 'day', name='uq_plant_analytics_plant_kind_day'),
        )
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
    if sa.inspect(op.get_bind()).has_table('plant_analytics'):
        op.drop_table('plant_analytics')
    for table, cols in _COLUMNS.items():
        have = _have(table)
        names = [c.name for c in cols if c.name in have]
        if not names:
            continue
        # create_all() builds these FKs unnamed, so find each by its column rather than by our name
        fks = {fk['constrained_columns'][0]: fk['name']
               for fk in sa.inspect(op.get_bind()).get_foreign_keys(table) if fk['constrained_columns']}
        with op.batch_alter_table(table) as batch:
            for n in names:
                if table == 'plant_alerts' and n in _FK and fks.get(n):
                    batch.drop_constraint(fks[n], type_='foreignkey')
                batch.drop_column(n)
