"""users, user_sessions, project_members, share_links (AXALON_AUTH_MODE=users)

Revision ID: 0009
Revises: 0008

Purely additive: nothing reads these tables unless AXALON_AUTH_MODE=users, so
applying it to an off/apikey deployment changes no behaviour.

Idempotent: `axalon.db.session.init_db` runs `Base.metadata.create_all()`, which
creates these tables whenever the app touches the database before migrations
run. A bare CREATE TABLE then fails, the startup hook only logs it, and the
database stays at 0008 with every later migration skipped.
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if name not in {ix['name'] for ix in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _inspector().has_table('users'):
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('email', sa.String(length=254), nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('role', sa.String(length=16), nullable=False, server_default='viewer'),
            sa.Column('disabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('email', name='uq_users_email'),
        )
    if not _inspector().has_table('user_sessions'):
        op.create_table(
            'user_sessions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('token_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token_hash', name='uq_user_sessions_token_hash'),
        )
    _create_index_if_missing('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    if not _inspector().has_table('project_members'):
        op.create_table(
            'project_members',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'project_id', name='uq_project_members_user_project'),
        )
    _create_index_if_missing('ix_project_members_user_id', 'project_members', ['user_id'])
    _create_index_if_missing('ix_project_members_project_id', 'project_members', ['project_id'])
    if not _inspector().has_table('share_links'):
        op.create_table(
            'share_links',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('token_hash', sa.String(length=64), nullable=False),
            sa.Column('project_id', sa.Integer(), nullable=False),
            sa.Column('label', sa.String(length=200), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token_hash', name='uq_share_links_token_hash'),
        )
    _create_index_if_missing('ix_share_links_project_id', 'share_links', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_share_links_project_id', 'share_links')
    op.drop_table('share_links')
    op.drop_index('ix_project_members_project_id', 'project_members')
    op.drop_index('ix_project_members_user_id', 'project_members')
    op.drop_table('project_members')
    op.drop_index('ix_user_sessions_user_id', 'user_sessions')
    op.drop_table('user_sessions')
    op.drop_table('users')
