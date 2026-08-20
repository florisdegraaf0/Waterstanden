from datetime import UTC, datetime

from app.domain.models import Measurement
from app.repositories.water import _chunks, _measurement_rows


def test_chunks_splits_values_into_fixed_size_batches() -> None:
    assert list(_chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_measurement_rows_deduplicates_by_database_conflict_key() -> None:
    measured_at = datetime(2026, 8, 18, tzinfo=UTC)
    first = Measurement(
        measured_at=measured_at,
        value=1.0,
        unit="m NAP",
        parameter="water_level",
    )
    second = Measurement(
        measured_at=measured_at,
        value=2.0,
        unit="m NAP",
        parameter="water_level",
    )

    rows = _measurement_rows(1, [first, second])

    assert len(rows) == 1
    assert rows[0]["value"] == 2.0


def test_measurement_rows_keep_parameters_separate_at_same_timestamp() -> None:
    measured_at = datetime(2026, 8, 18, tzinfo=UTC)

    rows = _measurement_rows(
        1,
        [
            Measurement(
                measured_at=measured_at,
                value=9.37,
                unit="m NAP",
                parameter="water_level",
            ),
            Measurement(
                measured_at=measured_at,
                value=2340,
                unit="m3/s",
                parameter="discharge",
            ),
        ],
    )

    assert len(rows) == 2
    assert {row["parameter"] for row in rows} == {"water_level", "discharge"}
