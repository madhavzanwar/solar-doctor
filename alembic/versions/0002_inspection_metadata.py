"""inspection_metadata

Revision ID: 0002
Revises: 0001_initial_schema
Create Date: 2026-06-01 17:21:31.431596

"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('inspections', sa.Column('client', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('location', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('capacity_mw', sa.Float(), nullable=True))
    op.add_column('inspections', sa.Column('inspection_type', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('inspection_level', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('irradiance_wm2', sa.Float(), nullable=True))
    op.add_column('inspections', sa.Column('wind_speed_bft', sa.Float(), nullable=True))
    op.add_column('inspections', sa.Column('cloud_coverage_okta', sa.Float(), nullable=True))


def downgrade() -> None:
    for col in ['cloud_coverage_okta', 'wind_speed_bft', 'irradiance_wm2',
                'inspection_level', 'inspection_type', 'capacity_mw', 'location', 'client']:
        op.drop_column('inspections', col)
