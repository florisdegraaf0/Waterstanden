"""Add station overview snapshots.

Revision ID: 0004_station_overview_snapshots
Revises: 0003_change_statistics
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_station_overview_snapshots"
down_revision: str | None = "0003_change_statistics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "station_overview_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("parameter", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_external_id", sa.String(), nullable=False),
        sa.Column("station_name", sa.String(), nullable=False),
        sa.Column("water_system", sa.String(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seasonal_percentile", sa.Float(), nullable=True),
        sa.Column("seasonal_status", sa.String(), nullable=False),
        sa.Column("anomaly_score", sa.Integer(), nullable=True),
        sa.Column("anomaly_severity", sa.String(), nullable=False),
        sa.Column("anomaly_status", sa.String(), nullable=False),
        sa.Column("anomaly_direction", sa.String(), nullable=True),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("data_quality_status", sa.String(), nullable=False),
        sa.Column("freshness_status", sa.String(), nullable=False),
        sa.Column("is_rankable", sa.Boolean(), nullable=False),
        sa.Column("delta_24h", sa.Float(), nullable=True),
        sa.Column("primary_signal", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("historical_years", sa.Integer(), nullable=False),
        sa.Column("historical_sample_size", sa.Integer(), nullable=False),
        sa.Column("recent_measurement_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id",
            "parameter",
            name="uq_station_overview_snapshots_station_parameter",
        ),
    )
    op.create_index(
        "ix_station_overview_snapshots_parameter_generated",
        "station_overview_snapshots",
        ["parameter", "generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_station_overview_snapshots_rank",
        "station_overview_snapshots",
        ["parameter", "is_rankable", "anomaly_score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_station_overview_snapshots_rank", table_name="station_overview_snapshots")
    op.drop_index(
        "ix_station_overview_snapshots_parameter_generated",
        table_name="station_overview_snapshots",
    )
    op.drop_table("station_overview_snapshots")
