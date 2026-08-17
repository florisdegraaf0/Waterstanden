"""Add historical measurement metadata and daily statistics.

Revision ID: 0002_historical_daily_statistics
Revises: 0001_initial_schema
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_historical_daily_statistics"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("measurements", sa.Column("quality_code", sa.String(), nullable=True))
    op.add_column("measurements", sa.Column("source_station_code", sa.String(), nullable=True))
    op.add_column("measurements", sa.Column("source_unit", sa.String(), nullable=True))
    op.add_column(
        "measurements",
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("measurements", "source_metadata", server_default=None)

    op.create_table(
        "station_daily_statistics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("parameter", sa.String(), nullable=False),
        sa.Column("min_value", sa.Float(), nullable=False),
        sa.Column("max_value", sa.Float(), nullable=False),
        sa.Column("mean_value", sa.Float(), nullable=False),
        sa.Column("median_value", sa.Float(), nullable=False),
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
            name="uq_station_daily_statistics_series_date",
        ),
    )
    op.create_index(
        "ix_station_daily_statistics_station_date",
        "station_daily_statistics",
        ["station_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_station_daily_statistics_station_date", table_name="station_daily_statistics")
    op.drop_table("station_daily_statistics")
    op.drop_column("measurements", "source_metadata")
    op.drop_column("measurements", "source_unit")
    op.drop_column("measurements", "source_station_code")
    op.drop_column("measurements", "quality_code")
