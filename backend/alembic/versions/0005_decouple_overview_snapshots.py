"""Decouple overview snapshots from station writes.

Revision ID: 0005_decouple_overview_snapshots
Revises: 0004_station_overview_snapshots
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_decouple_overview_snapshots"
down_revision: str | None = "0004_station_overview_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_station_overview_snapshots_station_parameter",
        "station_overview_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "station_overview_snapshots_station_id_fkey",
        "station_overview_snapshots",
        type_="foreignkey",
    )
    op.alter_column("station_overview_snapshots", "station_id", nullable=True)
    op.create_foreign_key(
        "station_overview_snapshots_station_id_fkey",
        "station_overview_snapshots",
        "stations",
        ["station_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_station_overview_snapshots_external_id_parameter",
        "station_overview_snapshots",
        ["station_external_id", "parameter"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_station_overview_snapshots_external_id_parameter",
        "station_overview_snapshots",
        type_="unique",
    )
    op.drop_constraint(
        "station_overview_snapshots_station_id_fkey",
        "station_overview_snapshots",
        type_="foreignkey",
    )
    op.alter_column("station_overview_snapshots", "station_id", nullable=False)
    op.create_foreign_key(
        "station_overview_snapshots_station_id_fkey",
        "station_overview_snapshots",
        "stations",
        ["station_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_station_overview_snapshots_station_parameter",
        "station_overview_snapshots",
        ["station_id", "parameter"],
    )
