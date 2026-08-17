from app.jobs.backfill_station import _is_selected_lobith_series


def test_lobith_filter_accepts_current_historical_series_metadata() -> None:
    assert _is_selected_lobith_series(
        {
            "station_code": "lobith.bovenrijn.tolkamer",
            "hoedanigheid": "NAP",
            "proces_type": "meting",
            "meetapparaat": "10042",
            "waardebepalingsmethode": None,
        }
    )


def test_lobith_filter_rejects_different_measurement_device() -> None:
    assert not _is_selected_lobith_series(
        {
            "station_code": "lobith.bovenrijn.tolkamer",
            "hoedanigheid": "NAP",
            "proces_type": "meting",
            "meetapparaat": "other",
            "waardebepalingsmethode": None,
        }
    )
