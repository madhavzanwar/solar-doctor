"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-23

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _create_index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    bind = op.get_bind()
    existing = {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("parks"):
        op.create_table(
            "parks",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("mode", sa.String(), nullable=True),
            sa.Column("total_panels", sa.Integer(), nullable=True),
            sa.Column("rows", sa.Integer(), nullable=True),
            sa.Column("cols", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("inspections"):
        op.create_table(
            "inspections",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("park_id", sa.String(), nullable=False),
            sa.Column("flight_date", sa.String(), nullable=True),
            sa.Column("total_images", sa.Integer(), nullable=True),
            sa.Column("total_detections", sa.Integer(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["park_id"], ["parks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("panel_faults"):
        op.create_table(
            "panel_faults",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("park_id", sa.String(), nullable=False),
            sa.Column("panel_id", sa.String(), nullable=False),
            sa.Column("class", sa.String(), nullable=False),
            sa.Column("class_id", sa.Integer(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("occurrences", sa.Integer(), nullable=True),
            sa.Column("max_confidence", sa.Float(), nullable=True),
            sa.Column("first_seen_inspection_id", sa.String(), nullable=True),
            sa.Column("last_seen_inspection_id", sa.String(), nullable=True),
            sa.Column("first_seen_date", sa.String(), nullable=True),
            sa.Column("last_seen_date", sa.String(), nullable=True),
            sa.Column("last_bbox", sa.Text(), nullable=True),
            sa.Column("last_gps", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["park_id"], ["parks.id"]),
            sa.ForeignKeyConstraint(["first_seen_inspection_id"], ["inspections.id"]),
            sa.ForeignKeyConstraint(["last_seen_inspection_id"], ["inspections.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_panel_faults_park_id", "panel_faults", ["park_id"])
    _create_index("ix_panel_faults_status", "panel_faults", ["status"])
    _create_index(
        "ix_panel_faults_identity",
        "panel_faults",
        ["park_id", "panel_id", "class"],
        unique=True,
    )

    if not _has_table("detections"):
        op.create_table(
            "detections",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("inspection_id", sa.String(), nullable=False),
            sa.Column("fault_id", sa.Integer(), nullable=True),
            sa.Column("image_id", sa.String(), nullable=True),
            sa.Column("panel_id", sa.String(), nullable=True),
            sa.Column("class", sa.String(), nullable=True),
            sa.Column("class_id", sa.Integer(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("bbox", sa.Text(), nullable=True),
            sa.Column("gps", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
            sa.ForeignKeyConstraint(["fault_id"], ["panel_faults.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_detections_fault_id", "detections", ["fault_id"])

    if not _has_table("corrections"):
        op.create_table(
            "corrections",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.String(), nullable=False),
            sa.Column("image_id", sa.String(), nullable=True),
            sa.Column("panel_id", sa.String(), nullable=True),
            sa.Column("class", sa.String(), nullable=False),
            sa.Column("class_id", sa.Integer(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("bbox_norm", sa.Text(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_corrections_job_id", "corrections", ["job_id"])

    if not _has_table("jobs"):
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("park_id", sa.String(), nullable=True),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("total", sa.Integer(), nullable=True),
            sa.Column("processed", sa.Integer(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("result_path", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index("ix_jobs_park_id", "jobs", ["park_id"])


def downgrade() -> None:
    for table in ("jobs", "corrections", "detections", "panel_faults", "inspections", "parks"):
        if _has_table(table):
            op.drop_table(table)
