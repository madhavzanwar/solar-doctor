"""inventory & prototype tracking

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'inventory_components',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('part_number', sa.String(), nullable=True),
        sa.Column('vendor', sa.String(), nullable=True),
        sa.Column('link', sa.String(), nullable=True),
        sa.Column('unit_cost', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(), nullable=True),
        sa.Column('qty_total', sa.Integer(), nullable=True),
        sa.Column('specs', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'prototypes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'component_assignments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('component_id', sa.Integer(), nullable=False),
        sa.Column('prototype_id', sa.Integer(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['component_id'], ['inventory_components.id']),
        sa.ForeignKeyConstraint(['prototype_id'], ['prototypes.id']),
    )
    op.create_index('ix_component_assignments_component_id', 'component_assignments', ['component_id'])
    op.create_index('ix_component_assignments_prototype_id', 'component_assignments', ['prototype_id'])
    op.create_table(
        'component_orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('component_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=True),
        sa.Column('est_unit_cost', sa.Float(), nullable=True),
        sa.Column('vendor', sa.String(), nullable=True),
        sa.Column('link', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('needed_by', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['component_id'], ['inventory_components.id']),
    )
    op.create_index('ix_component_orders_component_id', 'component_orders', ['component_id'])
    op.create_table(
        'track_notes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('tags', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'track_files',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_name', sa.String(), nullable=False),
        sa.Column('stored_name', sa.String(), nullable=False),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('content_type', sa.String(), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('track_files')
    op.drop_table('track_notes')
    op.drop_index('ix_component_orders_component_id', 'component_orders')
    op.drop_table('component_orders')
    op.drop_index('ix_component_assignments_prototype_id', 'component_assignments')
    op.drop_index('ix_component_assignments_component_id', 'component_assignments')
    op.drop_table('component_assignments')
    op.drop_table('prototypes')
    op.drop_table('inventory_components')
