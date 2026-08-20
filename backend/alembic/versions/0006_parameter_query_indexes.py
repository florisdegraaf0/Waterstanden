"""Add parameter-aware query indexes.

Revision ID: 0006_parameter_query_indexes
Revises: 0005_decouple_overview_snapshots
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_parameter_query_indexes"
down_revision: str | None = "0005_decouple_overview_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_measurements_station_parameter_measured_at",
        "measurements",
        ["station_id", "parameter", "measured_at"],
        unique=False,
    )
    op.create_index(
        "ix_station_daily_statistics_station_parameter_date",
        "station_daily_statistics",
        ["station_id", "parameter", "date"],
        unique=False,
    )
    op.create_index(
        "ix_station_historical_change_statistics_series_window_date",
        "station_historical_change_statistics",
        ["station_id", "parameter", "window_hours", "date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_station_historical_change_statistics_series_window_date",
        table_name="station_historical_change_statistics",
    )
    op.drop_index(
        "ix_station_daily_statistics_station_parameter_date",
        table_name="station_daily_statistics",
    )
    op.drop_index("ix_measurements_station_parameter_measured_at", table_name="measurements")
