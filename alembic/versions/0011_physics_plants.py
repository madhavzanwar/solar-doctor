"""physics tables: plants, inverters, strings, telemetry, forecasts, plant_alerts, diagnoses, weather_cache

Revision ID: 0011
Revises: 0010

Purely additive. `plants.park_id` is a unique FK to `parks.id` (Park <-> Plant 1:1).
Idempotent like 0009: `init_db()` runs `Base.metadata.create_all()`, which may already have
created these tables, so every create is guarded by has_table.

`telemetry` becomes a TimescaleDB hypertable only on PostgreSQL with the timescaledb extension
available; everywhere else it stays a plain table with an (plant_id, ts) index.
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

_TABLES = (
    'weather_cache', 'diagnoses', 'plant_alerts', 'forecasts', 'telemetry',
    'strings', 'inverters', 'plants',
)  # drop order (children first)


def _insp():
    return sa.inspect(op.get_bind())


def _tz():
    return sa.DateTime(timezone=True)


def _ix(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    if name not in {i['name'] for i in _insp().get_indexes(table)}:
        op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    if not _insp().has_table('plants'):
        op.create_table(
            'plants',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('park_id', sa.String(), nullable=True),
            sa.Column('name', sa.String(256), nullable=False),
            sa.Column('location', sa.String(512), nullable=True),
            sa.Column('lat', sa.Float(), nullable=False),
            sa.Column('lon', sa.Float(), nullable=False),
            sa.Column('tz', sa.String(64), nullable=False, server_default='UTC'),
            sa.Column('altitude_m', sa.Float(), nullable=False, server_default='0'),
            sa.Column('tilt', sa.Float(), nullable=False, server_default='20'),
            sa.Column('azimuth', sa.Float(), nullable=False, server_default='180'),
            sa.Column('dc_kw', sa.Float(), nullable=False),
            sa.Column('ac_kw', sa.Float(), nullable=False),
            sa.Column('module_count', sa.Integer(), nullable=True),
            sa.Column('module_wp', sa.Float(), nullable=True),
            sa.Column('temp_coeff', sa.Float(), nullable=False, server_default='-0.004'),
            sa.Column('tariff_inr_kwh', sa.Float(), nullable=True),
            sa.Column('source', sa.String(32), nullable=False, server_default='USER'),
            sa.Column('efficiency', sa.Float(), nullable=False, server_default='0.18'),
            sa.Column('soiling_threshold', sa.Float(), nullable=False, server_default='5'),
            sa.Column('clipping_threshold', sa.Float(), nullable=False, server_default='95'),
            sa.Column('forecast_horizon_minutes', sa.Integer(), nullable=False, server_default='60'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', _tz(), nullable=False),
            sa.Column('updated_at', _tz(), nullable=False),
            sa.ForeignKeyConstraint(['park_id'], ['parks.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('park_id', name='uq_plants_park_id'),
        )
    if not _insp().has_table('inverters'):
        op.create_table(
            'inverters',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('plant_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('ac_kw', sa.Float(), nullable=True),
            sa.Column('vendor', sa.String(64), nullable=True),
            sa.ForeignKeyConstraint(['plant_id'], ['plants.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    _ix('ix_inverters_plant_id', 'inverters', ['plant_id'])
    if not _insp().has_table('strings'):
        op.create_table(
            'strings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('plant_id', sa.Integer(), nullable=False),
            sa.Column('inverter_id', sa.Integer(), nullable=True),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('module_count', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['plant_id'], ['plants.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['inverter_id'], ['inverters.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
    _ix('ix_strings_plant_id', 'strings', ['plant_id'])
    _ix('ix_strings_inverter_id', 'strings', ['inverter_id'])
    if not _insp().has_table('telemetry'):
        op.create_table(
            'telemetry',
            sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
                      autoincrement=True, nullable=False),
            sa.Column('ts', _tz(), nullable=False),
            sa.Column('plant_id', sa.Integer(), nullable=False),
            sa.Column('inverter_id', sa.Integer(), nullable=True),
            sa.Column('string_id', sa.Integer(), nullable=True),
            sa.Column('p_ac_kw', sa.Float(), nullable=True),
            sa.Column('p_dc_kw', sa.Float(), nullable=True),
            sa.Column('v', sa.Float(), nullable=True),
            sa.Column('i', sa.Float(), nullable=True),
            sa.Column('poa_wm2', sa.Float(), nullable=True),
            sa.Column('ghi_wm2', sa.Float(), nullable=True),
            sa.Column('t_amb', sa.Float(), nullable=True),
            sa.Column('t_mod', sa.Float(), nullable=True),
            sa.Column('wind_ms', sa.Float(), nullable=True),
            sa.Column('p_expected_kw', sa.Float(), nullable=True),
            sa.Column('source', sa.String(32), nullable=False, server_default='USER'),
            sa.ForeignKeyConstraint(['plant_id'], ['plants.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['inverter_id'], ['inverters.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['string_id'], ['strings.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
    _ix('ix_telemetry_plant_ts', 'telemetry', ['plant_id', 'ts'])
    _maybe_hypertable()
    if not _insp().has_table('forecasts'):
        op.create_table(
            'forecasts',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('plant_id', sa.Integer(), nullable=False),
            sa.Column('forecast_time', _tz(), nullable=False),
            sa.Column('generated_at', _tz(), nullable=False),
            sa.Column('predicted_power_kw', sa.Float(), nullable=False),
            sa.Column('actual_power_kw', sa.Float(), nullable=True),
            sa.Column('confidence_lower', sa.Float(), nullable=True),
            sa.Column('confidence_upper', sa.Float(), nullable=True),
            sa.Column('model_name', sa.String(128), nullable=False),
            sa.Column('model_version', sa.String(64), nullable=False, server_default='1.0'),
            sa.Column('physics_power_kw', sa.Float(), nullable=True),
            sa.Column('ml_power_kw', sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(['plant_id'], ['plants.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    _ix('ix_forecasts_plant_time', 'forecasts', ['plant_id', 'forecast_time'])
    if not _insp().has_table('plant_alerts'):
        op.create_table(
            'plant_alerts',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('plant_id', sa.Integer(), nullable=False),
            sa.Column('timestamp', _tz(), nullable=False),
            sa.Column('alert_type', sa.String(64), nullable=False),
            sa.Column('severity', sa.String(32), nullable=False),
            sa.Column('message', sa.String(1024), nullable=False),
            sa.Column('expected_power_kw', sa.Float(), nullable=True),
            sa.Column('actual_power_kw', sa.Float(), nullable=True),
            sa.Column('deviation_percent', sa.Float(), nullable=True),
            sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('resolved_at', _tz(), nullable=True),
            sa.Column('created_at', _tz(), nullable=False),
            sa.Column('source', sa.String(32), nullable=False, server_default='USER'),
            sa.ForeignKeyConstraint(['plant_id'], ['plants.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    _ix('ix_plant_alerts_plant_ts', 'plant_alerts', ['plant_id', 'timestamp'])
    if not _insp().has_table('diagnoses'):
        op.create_table(
            'diagnoses',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('plant_id', sa.Integer(), nullable=False),
            sa.Column('alert_id', sa.Integer(), nullable=True),
            sa.Column('timestamp', _tz(), nullable=False),
            sa.Column('root_cause_category', sa.String(64), nullable=False),
            sa.Column('root_cause_title', sa.String(255), nullable=False),
            sa.Column('confidence_score', sa.Float(), nullable=False),
            sa.Column('inverter_error_code', sa.String(64), nullable=True),
            sa.Column('estimated_loss_kw', sa.Float(), nullable=False, server_default='0'),
            sa.Column('financial_impact_per_day', sa.Float(), nullable=False, server_default='0'),
            sa.Column('urgency_level', sa.String(32), nullable=False, server_default='MEDIUM'),
            sa.Column('summary', sa.String(1024), nullable=False),
            sa.Column('root_cause_details', sa.Text(), nullable=False),
            sa.Column('technician_steps_json', sa.Text(), nullable=False),
            sa.Column('safety_warning', sa.String(512), nullable=True),
            sa.Column('preventative_advice', sa.String(512), nullable=True),
            sa.Column('telemetry_ts', _tz(), nullable=True),
            sa.Column('telemetry_source', sa.String(32), nullable=True),
            sa.Column('created_at', _tz(), nullable=False),
            sa.ForeignKeyConstraint(['plant_id'], ['plants.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['alert_id'], ['plant_alerts.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
    _ix('ix_diagnoses_plant_ts', 'diagnoses', ['plant_id', 'timestamp'])
    _ix('ix_diagnoses_alert_id', 'diagnoses', ['alert_id'])
    if not _insp().has_table('weather_cache'):
        op.create_table(
            'weather_cache',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('lat_key', sa.Float(), nullable=False),
            sa.Column('lon_key', sa.Float(), nullable=False),
            sa.Column('kind', sa.String(32), nullable=False),
            sa.Column('source', sa.String(64), nullable=False),
            sa.Column('payload_json', sa.Text(), nullable=False),
            sa.Column('fetched_at', _tz(), nullable=False),
            sa.Column('expires_at', _tz(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('lat_key', 'lon_key', 'kind', name='uq_weather_cache_key'),
        )


def _maybe_hypertable() -> None:
    """Convert telemetry to a Timescale hypertable (PostgreSQL + extension available only).

    Hypertable unique keys must include the time column, so the PK becomes (id, ts) first.
    Not exercised by the SQLite test-suite; verify on a Timescale instance before relying on it.
    """
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    avail = bind.execute(sa.text(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")).first()
    if not avail:
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("ALTER TABLE telemetry DROP CONSTRAINT IF EXISTS telemetry_pkey")
    op.execute("ALTER TABLE telemetry ADD PRIMARY KEY (id, ts)")
    op.execute("SELECT create_hypertable('telemetry', 'ts', if_not_exists => TRUE, migrate_data => TRUE)")


def downgrade() -> None:
    for name in _TABLES:
        if _insp().has_table(name):
            op.drop_table(name)
