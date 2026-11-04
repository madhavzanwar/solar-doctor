"""projects + parks.project_id (Area C asset hierarchy)

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('client', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    # batch_alter_table: SQLite cannot ALTER constraints in place (it rebuilds the
    # table); on PostgreSQL this emits the same plain ALTER statements as before.
    with op.batch_alter_table('parks') as batch:
        batch.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch.create_index('ix_parks_project_id', ['project_id'])
        batch.create_foreign_key('fk_parks_project_id', 'projects', ['project_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('parks') as batch:
        batch.drop_constraint('fk_parks_project_id', type_='foreignkey')
        batch.drop_index('ix_parks_project_id')
        batch.drop_column('project_id')
    op.drop_table('projects')
