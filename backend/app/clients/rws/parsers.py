import csv
import io
import re
from datetime import datetime
from typing import Any

from app.clients.rws.models import RwsLatestObservation
from app.domain.models import Measurement
from app.exceptions import ExternalDataError

ALLOWED_QUALITY_CODES = {"00", "10", "20", "25", "30", "40"}
WATER_LEVEL_CODE = "WATHTE"
SURFACE_WATER_CODE = "OW"

_POINT_RE = re.compile(
    r"^POINT\s*\(\s*(?P<latitude>-?\d+(?:\.\d+)?)\s+(?P<longitude>-?\d+(?:\.\d+)?)\s*\)$"
)


def parse_latest_observations_csv(csv_text: str) -> list[RwsLatestObservation]:
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    observations: list[RwsLatestObservation] = []

    for row in reader:
        parsed = _parse_latest_observation_row(row)
        if parsed is not None:
            observations.append(parsed)

    return observations


def normalize_latest_water_level(row: RwsLatestObservation) -> Measurement | None:
    if row.value is None:
        return None
    if row.unit_code == "cm":
        value = row.value / 100
    else:
        value = row.value
    if row.measured_at is None:
        return None
    return Measurement(
        measured_at=row.measured_at,
        value=value,
        unit=_display_unit(row.unit_code, row.hoedanigheid_code),
        parameter="water_level",
        quality_code=row.quality_code,
    )


def parse_observations_response(payload: dict[str, Any]) -> list[Measurement]:
    measurements: list[Measurement] = []
    for series in payload.get("WaarnemingenLijst", []):
        metadata = series.get("AquoMetadata", {})
        unit_code = _nested_code(metadata, "Eenheid")
        hoedanigheid_code = _nested_code(metadata, "Hoedanigheid")
        unit = _display_unit(unit_code, hoedanigheid_code)
        parameter = _parameter_name(_nested_code(metadata, "Grootheid"))

        for item in series.get("MetingenLijst", []):
            value = _parse_optional_float(item.get("Meetwaarde", {}).get("Waarde_Numeriek"))
            measured_at = _parse_datetime(item.get("Tijdstip"))
            if value is None or measured_at is None:
                continue
            if unit_code == "cm":
                value = value / 100
            measurements.append(
                Measurement(
                    measured_at=measured_at,
                    value=value,
                    unit=unit,
                    parameter=parameter,
                    quality_code=item.get("Kwaliteitswaarde", {}).get("Code"),
                )
            )

    return sorted(measurements, key=lambda measurement: measurement.measured_at)


def _parse_latest_observation_row(row: dict[str, str]) -> RwsLatestObservation | None:
    if row.get("GROOTHEIDCODE") != WATER_LEVEL_CODE:
        return None
    if row.get("COMPARTIMENTCODE") != SURFACE_WATER_CODE:
        return None
    quality_code = _blank_to_none(row.get("KWALITEITSWAARDE_CODE"))
    if quality_code and quality_code not in ALLOWED_QUALITY_CODES:
        return None

    code = _required(row, "CODE")
    name = _required(row, "NAAM")
    latitude, longitude = _parse_point(_required(row, "GEOMETRY"))

    return RwsLatestObservation(
        code=code,
        name=name,
        latitude=latitude,
        longitude=longitude,
        value=_parse_optional_float(row.get("WAARDE_LAATSTE_METING")),
        unit_code=_blank_to_none(row.get("EENHEIDCODE")),
        measured_at=_parse_datetime(row.get("TIJDSTIP_LAATSTE_METING")),
        parameter_description=_required(row, "PARAMETER_WAT_OMSCHRIJVING"),
        status=_blank_to_none(row.get("STATUSWAARDE")),
        quality_code=quality_code,
        grootheid_code=_required(row, "GROOTHEIDCODE"),
        compartiment_code=_required(row, "COMPARTIMENTCODE"),
        hoedanigheid_code=_blank_to_none(row.get("HOEDANIGHEIDCODE")),
        raw_metadata={
            "source_unit": _blank_to_none(row.get("EENHEIDCODE")),
            "source_parameter": _blank_to_none(row.get("GROOTHEIDCODE")),
            "source_description": _blank_to_none(row.get("PARAMETER_WAT_OMSCHRIJVING")),
            "status": _blank_to_none(row.get("STATUSWAARDE")),
            "quality_code": quality_code,
            "reference": _blank_to_none(row.get("HOEDANIGHEIDCODE")),
            "source": "rws_ddapi20_wfs_locatiesmetlaatstewaarneming",
        },
    )


def _parse_point(value: str) -> tuple[float, float]:
    match = _POINT_RE.match(value)
    if match is None:
        raise ExternalDataError(f"Invalid RWS geometry: {value!r}")
    return float(match.group("latitude")), float(match.group("longitude"))


def _parse_datetime(value: str | None) -> datetime | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalDataError(f"Invalid RWS timestamp: {value!r}") from exc


def _parse_optional_float(value: str | int | float | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ExternalDataError(f"Invalid RWS numeric value: {value!r}") from exc


def _required(row: dict[str, str], field: str) -> str:
    value = _blank_to_none(row.get(field))
    if value is None:
        raise ExternalDataError(f"Missing required RWS field: {field}")
    return value


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _nested_code(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, dict):
        code = value.get("Code")
        return str(code) if code is not None else None
    return None


def _display_unit(unit_code: str | None, hoedanigheid_code: str | None) -> str:
    if unit_code == "cm":
        return "m NAP" if hoedanigheid_code == "NAP" else "m"
    return unit_code or ""


def _parameter_name(grootheid_code: str | None) -> str:
    if grootheid_code == WATER_LEVEL_CODE:
        return "water_level"
    return grootheid_code or "unknown"

