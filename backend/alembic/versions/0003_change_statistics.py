"""Add historical change statistics.

Revision ID: 0003_change_statistics
Revises: 0002_historical_daily_statistics
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_change_statistics"
down_revision: str | None = "0002_historical_daily_statistics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "station_historical_change_statistics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("parameter", sa.String(), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False),
        sa.Column("delta_value", sa.Float(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
            "date",
            "window_hours",
            name="uq_station_historical_change_statistics_series_date",
        ),
    )
    op.create_index(
        "ix_station_historical_change_statistics_station_date",
        "station_historical_change_statistics",
        ["station_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_station_historical_change_statistics_station_date",
        table_name="station_historical_change_statistics",
    )
    op.drop_table("station_historical_change_statistics")
