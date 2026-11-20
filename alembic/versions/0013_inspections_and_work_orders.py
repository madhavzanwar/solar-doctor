"""inspections single-image/fusion/roi columns, panel_faults work order lifecycle and verification columns, fault_photos photo_type, plants ROI settings

Revision ID: 0013
Revises: 0012

Additive. Idempotent like 0012: `create_all()` may already have created the columns, so each add is
guarded by a column check. batch_alter_table keeps SQLite working.
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

_FK = {
    'inspections': {
        'plant_id': ('plants', 'fk_inspections_plant_id'),
        'string_id': ('strings', 'fk_inspections_string_id'),
        'alert_id': ('plant_alerts', 'fk_inspections_alert_id'),
    },
    'panel_faults': {
        'plant_id': ('plants', 'fk_panel_faults_plant_id'),
        'string_id': ('strings', 'fk_panel_faults_string_id'),
        'alert_id': ('plant_alerts', 'fk_panel_faults_alert_id'),
        'inspection_id': ('inspections', 'fk_panel_faults_inspection_id'),
    },
}

_COLUMNS = {
    'inspections': [
        sa.Column('plant_id', sa.Integer(), nullable=True),
        sa.Column('string_id', sa.Integer(), nullable=True),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('image_path', sa.String(512), nullable=True),
        sa.Column('image_sha256', sa.String(64), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(32), nullable=False, server_default='upload'),
        sa.Column('model_version', sa.String(64), nullable=True),
        sa.Column('predicted_class', sa.String(64), nullable=True),
        sa.Column('probs_json', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('ood_score', sa.Float(), nullable=True),
        sa.Column('needs_field_check', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('field_check_reason', sa.Text(), nullable=True),
        sa.Column('xai_gradcam_path', sa.String(512), nullable=True),
        sa.Column('xai_lime_path', sa.String(512), nullable=True),
        sa.Column('fused_verdict', sa.String(64), nullable=True),
        sa.Column('fused_action', sa.String(64), nullable=True),
        sa.Column('fused_severity', sa.String(32), nullable=True),
        sa.Column('fused_reason', sa.Text(), nullable=True),
        sa.Column('recoverable_kwh_day', sa.Float(), nullable=True),
        sa.Column('recoverable_inr_day', sa.Float(), nullable=True),
        sa.Column('payback_days', sa.Float(), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='completed'),
    ],
    'panel_faults': [
        sa.Column('plant_id', sa.Integer(), nullable=True),
        sa.Column('string_id', sa.Integer(), nullable=True),
        sa.Column('alert_id', sa.Integer(), nullable=True),
        sa.Column('inspection_id', sa.String(128), nullable=True),
        sa.Column('checklist', sa.Text(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pi_before', sa.Float(), nullable=True),
        sa.Column('pi_after', sa.Float(), nullable=True),
        sa.Column('recovery_percent', sa.Float(), nullable=True),
        sa.Column('before_photo_path', sa.String(512), nullable=True),
        sa.Column('after_photo_path', sa.String(512), nullable=True),
    ],
    'fault_photos': [
        sa.Column('photo_type', sa.String(32), nullable=False, server_default='proof'),
    ],
    'plants': [
        sa.Column('cleaning_cost_per_module_inr', sa.Float(), nullable=False, server_default='50.0'),
        sa.Column('water_l_per_module', sa.Float(), nullable=False, server_default='2.5'),
        sa.Column('water_cost_inr_per_l', sa.Float(), nullable=False, server_default='0.05'),
        sa.Column('labour_cost_inr', sa.Float(), nullable=False, server_default='1500.0'),
        sa.Column('tariff_preset', sa.String(32), nullable=False, server_default='c_and_i'),
    ],
}


def _have(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c['name'] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def upgrade() -> None:
    for table, cols in _COLUMNS.items():
        have = _have(table)
        todo = [c for c in cols if c.name not in have]
        if not have:
            continue
        with op.batch_alter_table(table) as batch:
            if table == 'inspections' and 'park_id' in have:
                batch.alter_column('park_id', existing_type=sa.String(), nullable=True)
            for c in todo:
                batch.add_column(c)
                if table in _FK and c.name in _FK[table]:
                    ref, name = _FK[table][c.name]
                    batch.create_foreign_key(name, ref, [c.name], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    for table, cols in _COLUMNS.items():
        have = _have(table)
        names = [c.name for c in cols if c.name in have]
        if not names:
            continue
        fks = {fk['constrained_columns'][0]: fk['name']
               for fk in sa.inspect(op.get_bind()).get_foreign_keys(table) if fk['constrained_columns']}
        with op.batch_alter_table(table) as batch:
            for n in names:
                if table in _FK and n in _FK[table] and fks.get(n):
                    batch.drop_constraint(fks[n], type_='foreignkey')
                batch.drop_column(n)
