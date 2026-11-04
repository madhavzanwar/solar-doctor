"""fault_comments

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-01 17:21:43.023943

"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fault_comments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('fault_id', sa.Integer(), sa.ForeignKey('panel_faults.id'), nullable=False),
        sa.Column('author', sa.String(128), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fault_comments_fault_id', 'fault_comments', ['fault_id'])


def downgrade() -> None:
    op.drop_index('ix_fault_comments_fault_id', 'fault_comments')
    op.drop_table('fault_comments')
