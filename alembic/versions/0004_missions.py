"""missions

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'missions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('park_id', sa.String(), nullable=True),
        sa.Column('mission_type', sa.String(), nullable=True),
        sa.Column('camera_id', sa.String(), nullable=True),
        sa.Column('params', sa.Text(), nullable=True),
        sa.Column('polygon', sa.Text(), nullable=True),
        sa.Column('waypoints', sa.Text(), nullable=True),
        sa.Column('area_ha', sa.Float(), nullable=True),
        sa.Column('image_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_missions_park_id', 'missions', ['park_id'])


def downgrade() -> None:
    op.drop_index('ix_missions_park_id', 'missions')
    op.drop_table('missions')
