from datetime import UTC, date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StationRecord(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    location: Mapped[Any] = mapped_column(Geometry(geometry_type="POINT", srid=4326))
    station_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    measurements: Mapped[list["MeasurementRecord"]] = relationship(back_populates="station")


class MeasurementRecord(Base):
    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "parameter",
            "measured_at",
            name="uq_measurement_series_time",
        ),
        Index("ix_measurements_station_measured_at", "station_id", "measured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float]
    unit: Mapped[str]
    parameter: Mapped[str]
    quality_code: Mapped[str | None]
    source_station_code: Mapped[str | None]
    source_unit: Mapped[str | None]
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    station: Mapped[StationRecord] = relationship(back_populates="measurements")


Index("ix_stations_location", StationRecord.location, postgresql_using="gist")


class StationDailyStatisticRecord(Base):
    __tablename__ = "station_daily_statistics"
    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "parameter",
            "date",
            name="uq_station_daily_statistics_series_date",
        ),
        Index(
            "ix_station_daily_statistics_station_date",
            "station_id",
            "date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    parameter: Mapped[str]
    min_value: Mapped[float]
    max_value: Mapped[float]
    mean_value: Mapped[float]
    median_value: Mapped[float]
    observation_count: Mapped[int]
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
