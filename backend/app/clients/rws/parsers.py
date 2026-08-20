import csv
import io
import re
from datetime import datetime
from typing import Any

from app.clients.rws.models import RwsLatestObservation
from app.domain.models import Measurement
from app.domain.parameters import (
    parameter_from_rws_grootheid,
    parameter_metadata,
)
from app.exceptions import ExternalDataError

ALLOWED_QUALITY_CODES = {"00", "10", "20", "25", "30", "40"}
WATER_LEVEL_CODE = "WATHTE"
DISCHARGE_CODE = "Q"
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


def normalize_latest_observation(row: RwsLatestObservation) -> Measurement | None:
    if row.value is None:
        return None
    if row.measured_at is None:
        return None
    parameter = parameter_from_rws_grootheid(row.grootheid_code)
    metadata = parameter_metadata(parameter)
    unit_code = row.unit_code or ""
    if unit_code not in metadata.accepted_source_units:
        raise ExternalDataError(
            f"Unexpected RWS unit {unit_code!r} for parameter {parameter!r}"
        )
    return Measurement(
        measured_at=row.measured_at,
        value=_normalize_value(row.value, unit_code),
        unit=_display_unit(unit_code, row.hoedanigheid_code),
        parameter=parameter,
        quality_code=row.quality_code,
    )


def normalize_latest_water_level(row: RwsLatestObservation) -> Measurement | None:
    measurement = normalize_latest_observation(row)
    if measurement is None or measurement.parameter != "water_level":
        return None
    return measurement


def parse_observations_response(payload: dict[str, Any]) -> list[Measurement]:
    measurements: list[Measurement] = []
    for series in payload.get("WaarnemingenLijst", []):
        metadata = series.get("AquoMetadata", {})
        location = series.get("Locatie", {})
        unit_code = _nested_code(metadata, "Eenheid")
        hoedanigheid_code = _nested_code(metadata, "Hoedanigheid")
        parameter = parameter_from_rws_grootheid(_nested_code(metadata, "Grootheid"))
        parameter_info = parameter_metadata(parameter)
        if unit_code not in parameter_info.accepted_source_units:
            raise ExternalDataError(
                f"Unexpected RWS unit {unit_code!r} for parameter {parameter!r}"
            )
        unit = _display_unit(unit_code, hoedanigheid_code)
        source_metadata = _source_metadata(series)

        for item in series.get("MetingenLijst", []):
            value = _parse_optional_float(item.get("Meetwaarde", {}).get("Waarde_Numeriek"))
            measured_at = _parse_datetime(item.get("Tijdstip"))
            if value is None or measured_at is None:
                continue
            measurements.append(
                Measurement(
                    measured_at=measured_at,
                    value=_normalize_value(value, unit_code),
                    unit=unit,
                    parameter=parameter,
                    quality_code=_measurement_quality_code(item),
                    source_station_code=_blank_to_none(location.get("Code")),
                    source_unit=unit_code,
                    source_metadata=source_metadata,
                )
            )

    return sorted(measurements, key=lambda measurement: measurement.measured_at)


def _parse_latest_observation_row(row: dict[str, str]) -> RwsLatestObservation | None:
    grootheid_code = row.get("GROOTHEIDCODE")
    try:
        parameter = parameter_from_rws_grootheid(grootheid_code)
    except ExternalDataError:
        return None
    metadata = parameter_metadata(parameter)
    if row.get("COMPARTIMENTCODE") != metadata.rws_compartiment_code:
        return None
    hoedanigheid_code = _blank_to_none(row.get("HOEDANIGHEIDCODE"))
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
        hoedanigheid_code=hoedanigheid_code,
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


def _measurement_quality_code(item: dict[str, Any]) -> str | None:
    legacy = item.get("Kwaliteitswaarde")
    if isinstance(legacy, dict):
        code = legacy.get("Code")
        if code is not None:
            return str(code)

    metadata = item.get("WaarnemingMetadata")
    if isinstance(metadata, dict):
        quality = metadata.get("Kwaliteitswaardecode")
        if isinstance(quality, dict):
            code = quality.get("Code")
            return str(code) if code is not None else None
    return None


def _source_metadata(series: dict[str, Any]) -> dict[str, str | float | None]:
    metadata = series.get("AquoMetadata", {})
    location = series.get("Locatie", {})
    observation_metadata = series.get("WaarnemingMetadata", {})
    return {
        "source": "rws_ddapi20_waterwebservices_observations",
        "station_code": _blank_to_none(location.get("Code")),
        "station_name": _blank_to_none(location.get("Naam")),
        "unit": _nested_code(metadata, "Eenheid"),
        "grootheid": _nested_code(metadata, "Grootheid"),
        "compartiment": _nested_code(metadata, "Compartiment"),
        "hoedanigheid": _nested_code(metadata, "Hoedanigheid"),
        "proces_type": (
            metadata.get("ProcesType") if isinstance(metadata.get("ProcesType"), str) else None
        ),
        "meetapparaat": _nested_code(metadata, "MeetApparaat"),
        "waardebepalingsmethode": _nested_code(metadata, "WaardeBepalingsmethode"),
        "waardebewerkingsmethode": _nested_code(metadata, "WaardeBewerkingsmethode"),
        "opdrachtgevende_instantie": _first_nested_code(
            observation_metadata,
            "OpdrachtgevendeInstantieLijst",
        ),
        "bemonsteringshoogte": _first_value(observation_metadata, "BemonsteringshoogteLijst"),
    }


def _first_nested_code(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        code = value[0].get("Code")
        return str(code) if code is not None else None
    return None


def _first_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _display_unit(unit_code: str | None, hoedanigheid_code: str | None) -> str:
    if unit_code == "cm":
        return "m NAP" if hoedanigheid_code == "NAP" else "m"
    return unit_code or ""


def _normalize_value(value: float, unit_code: str | None) -> float:
    if unit_code == "cm":
        return value / 100
    return value
