from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.exceptions import ExternalDataError

MeasurementParameter = Literal["water_level", "discharge"]


@dataclass(frozen=True)
class ParameterMetadata:
    code: MeasurementParameter
    label: str
    default_unit: str
    rws_grootheid_code: str
    rws_compartiment_code: str
    rws_hoedanigheid_code: str | None
    accepted_source_units: frozenset[str]
    historical_aggregation: str


SUPPORTED_PARAMETERS: dict[MeasurementParameter, ParameterMetadata] = {
    "water_level": ParameterMetadata(
        code="water_level",
        label="Water level",
        default_unit="m NAP",
        rws_grootheid_code="WATHTE",
        rws_compartiment_code="OW",
        rws_hoedanigheid_code="NAP",
        accepted_source_units=frozenset({"cm"}),
        historical_aggregation="daily_mean",
    ),
    "discharge": ParameterMetadata(
        code="discharge",
        label="Discharge",
        default_unit="m3/s",
        rws_grootheid_code="Q",
        rws_compartiment_code="OW",
        rws_hoedanigheid_code=None,
        accepted_source_units=frozenset({"m3/s"}),
        historical_aggregation="daily_mean",
    ),
}

RWS_GROOTHEID_TO_PARAMETER: dict[str, MeasurementParameter] = {
    metadata.rws_grootheid_code: parameter
    for parameter, metadata in SUPPORTED_PARAMETERS.items()
}


def validate_parameter(parameter: str) -> MeasurementParameter:
    if parameter in SUPPORTED_PARAMETERS:
        return parameter  # type: ignore[return-value]
    supported = ", ".join(sorted(SUPPORTED_PARAMETERS))
    raise ValueError(f"Unsupported parameter {parameter!r}; expected one of: {supported}")


def parameter_metadata(parameter: str) -> ParameterMetadata:
    return SUPPORTED_PARAMETERS[validate_parameter(parameter)]


def parameter_from_rws_grootheid(grootheid_code: str | None) -> MeasurementParameter:
    if grootheid_code is None:
        raise ExternalDataError("Missing RWS Grootheid code")
    parameter = RWS_GROOTHEID_TO_PARAMETER.get(grootheid_code)
    if parameter is None:
        raise ExternalDataError(f"Unsupported RWS Grootheid code: {grootheid_code!r}")
    return parameter
