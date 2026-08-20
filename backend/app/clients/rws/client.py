import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.clients.rws.models import RwsLatestObservation
from app.clients.rws.parsers import parse_latest_observations_csv, parse_observations_response
from app.config import Settings
from app.domain.models import Measurement
from app.domain.parameters import parameter_metadata
from app.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

_MAX_WFS_RESPONSE_BYTES = 5_000_000

_LATEST_LOCATION_PROPERTIES = (
    "CODE",
    "NAAM",
    "GEOMETRY",
    "WAARDE_LAATSTE_METING",
    "EENHEIDCODE",
    "TIJDSTIP_LAATSTE_METING",
    "PARAMETER_WAT_OMSCHRIJVING",
    "STATUSWAARDE",
    "KWALITEITSWAARDE_CODE",
    "GROOTHEIDCODE",
    "COMPARTIMENTCODE",
    "HOEDANIGHEIDCODE",
)


class RwsClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = http_client or httpx.AsyncClient(timeout=settings.rws_timeout_seconds)
        self._owns_client = http_client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_latest_water_level_locations(self) -> list[RwsLatestObservation]:
        return await self.fetch_latest_locations("water_level")

    async def fetch_latest_locations(
        self,
        parameter: str = "water_level",
    ) -> list[RwsLatestObservation]:
        metadata = parameter_metadata(parameter)
        params = {
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": "locatiesmetlaatstewaarneming",
            "FILTER": _latest_location_filter(
                grootheid_code=metadata.rws_grootheid_code,
                compartiment_code=metadata.rws_compartiment_code,
            ),
            "PROPERTYNAME": ",".join(_LATEST_LOCATION_PROPERTIES),
            "MAXFEATURES": str(self._settings.rws_wfs_max_features),
            "outputFormat": "csv",
            "format_options": "csvseparator:semicolon",
        }
        try:
            async with self._client.stream(
                "GET", self._settings.rws_wfs_base_url, params=params
            ) as response:
                response.raise_for_status()
                csv_text = await _read_limited_text(response, _MAX_WFS_RESPONSE_BYTES)
        except httpx.HTTPError as exc:
            logger.warning("RWS WFS latest observations request failed", exc_info=exc)
            message = "Rijkswaterstaat latest observations are unavailable"
            raise ExternalServiceError(message) from exc

        return parse_latest_observations_csv(csv_text)

    async def fetch_recent_measurements(
        self,
        station_code: str,
        hours: int,
        parameter: str = "water_level",
    ) -> list[Measurement]:
        end = datetime.now(UTC)
        begin = end - timedelta(hours=hours)
        payload = _observations_payload(
            station_code=station_code,
            begin=begin,
            end=end,
            parameter=parameter,
        )
        url = (
            f"{self._settings.rws_waterwebservices_base_url}"
            "/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
        )
        try:
            response = await self._client.post(url, json=payload)
            if response.status_code == 204:
                return []
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "RWS recent observations request failed",
                extra={"station_code": station_code, "hours": hours, "parameter": parameter},
                exc_info=exc,
            )
            message = "Rijkswaterstaat recent observations are unavailable"
            raise ExternalServiceError(message) from exc

        return _filter_parameter_measurements(
            parse_observations_response(response.json()),
            parameter,
        )

    async def fetch_historical_measurements(
        self,
        station_code: str,
        begin: datetime,
        end: datetime,
        parameter: str = "water_level",
    ) -> list[Measurement]:
        payload = _observations_payload(
            station_code=station_code,
            begin=begin,
            end=end,
            parameter=parameter,
        )
        url = (
            f"{self._settings.rws_waterwebservices_base_url}"
            "/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
        )
        try:
            response = await self._client.post(url, json=payload)
            if response.status_code == 204:
                return []
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "RWS historical observations request failed",
                extra={
                    "station_code": station_code,
                    "parameter": parameter,
                    "begin": begin.isoformat(),
                    "end": end.isoformat(),
                },
                exc_info=exc,
            )
            message = "Rijkswaterstaat historical observations are unavailable"
            raise ExternalServiceError(message) from exc

        return _filter_parameter_measurements(
            parse_observations_response(response.json()),
            parameter,
        )


def _latest_location_filter(*, grootheid_code: str, compartiment_code: str) -> str:
    return (
        "<Filter>"
        "<And>"
        "<PropertyIsEqualTo>"
        "<PropertyName>GROOTHEIDCODE</PropertyName>"
        f"<Literal>{grootheid_code}</Literal>"
        "</PropertyIsEqualTo>"
        "<PropertyIsEqualTo>"
        "<PropertyName>COMPARTIMENTCODE</PropertyName>"
        f"<Literal>{compartiment_code}</Literal>"
        "</PropertyIsEqualTo>"
        "</And>"
        "</Filter>"
    )


def _observations_payload(
    *,
    station_code: str,
    begin: datetime,
    end: datetime,
    parameter: str,
) -> dict[str, Any]:
    metadata = parameter_metadata(parameter)
    aquo_metadata: dict[str, Any] = {
        "Compartiment": {"Code": metadata.rws_compartiment_code},
        "Grootheid": {"Code": metadata.rws_grootheid_code},
        "ProcesType": "meting",
    }
    if metadata.rws_hoedanigheid_code is not None:
        aquo_metadata["Hoedanigheid"] = {"Code": metadata.rws_hoedanigheid_code}

    return {
        "Locatie": {"Code": station_code},
        "AquoPlusWaarnemingMetadata": {
            "AquoMetadata": aquo_metadata,
            "WaarnemingMetadata": {
                "KwaliteitswaardecodeLijst": ["00", "10", "20", "25", "30", "40"]
            },
        },
        "Periode": {
            "Begindatumtijd": _rws_datetime(begin),
            "Einddatumtijd": _rws_datetime(end),
        },
    }


def _rws_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _read_limited_text(response: httpx.Response, max_bytes: int) -> str:
    chunks: list[bytes] = []
    total_bytes = 0

    async for chunk in response.aiter_bytes():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            message = "Rijkswaterstaat WFS response exceeded the configured size limit"
            raise ExternalServiceError(message)
        chunks.append(chunk)

    content = b"".join(chunks)
    return content.decode(response.encoding or "utf-8", errors="replace")


def _filter_parameter_measurements(
    measurements: list[Measurement],
    parameter: str,
) -> list[Measurement]:
    metadata = parameter_metadata(parameter)
    return [
        measurement
        for measurement in measurements
        if measurement.parameter == metadata.code
        and (
            metadata.rws_hoedanigheid_code is None
            or (measurement.source_metadata or {}).get("hoedanigheid")
            == metadata.rws_hoedanigheid_code
        )
    ]
