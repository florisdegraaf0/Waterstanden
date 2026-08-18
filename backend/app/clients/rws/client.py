import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.clients.rws.models import RwsLatestObservation
from app.clients.rws.parsers import parse_latest_observations_csv, parse_observations_response
from app.config import Settings
from app.domain.models import Measurement
from app.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

_MAX_WFS_RESPONSE_BYTES = 5_000_000

_LATEST_WATER_LEVEL_FILTER = (
    "<Filter>"
    "<And>"
    "<PropertyIsEqualTo>"
    "<PropertyName>GROOTHEIDCODE</PropertyName>"
    "<Literal>WATHTE</Literal>"
    "</PropertyIsEqualTo>"
    "<PropertyIsEqualTo>"
    "<PropertyName>COMPARTIMENTCODE</PropertyName>"
    "<Literal>OW</Literal>"
    "</PropertyIsEqualTo>"
    "</And>"
    "</Filter>"
)

_LATEST_WATER_LEVEL_PROPERTIES = (
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
        params = {
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": "locatiesmetlaatstewaarneming",
            "FILTER": _LATEST_WATER_LEVEL_FILTER,
            "PROPERTYNAME": ",".join(_LATEST_WATER_LEVEL_PROPERTIES),
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

    async def fetch_recent_measurements(self, station_code: str, hours: int) -> list[Measurement]:
        end = datetime.now(UTC)
        begin = end - timedelta(hours=hours)
        payload: dict[str, Any] = {
            "Locatie": {"Code": station_code},
            "AquoPlusWaarnemingMetadata": {
                "AquoMetadata": {
                    "Compartiment": {"Code": "OW"},
                    "Grootheid": {"Code": "WATHTE"},
                    "ProcesType": "meting",
                    "Hoedanigheid": {"Code": "NAP"},
                },
                "WaarnemingMetadata": {
                    "KwaliteitswaardecodeLijst": ["00", "10", "20", "25", "30", "40"]
                },
            },
            "Periode": {
                "Begindatumtijd": _rws_datetime(begin),
                "Einddatumtijd": _rws_datetime(end),
            },
        }
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
                extra={"station_code": station_code, "hours": hours},
                exc_info=exc,
            )
            message = "Rijkswaterstaat recent observations are unavailable"
            raise ExternalServiceError(message) from exc

        return _nap_water_level_measurements(parse_observations_response(response.json()))

    async def fetch_historical_measurements(
        self,
        station_code: str,
        begin: datetime,
        end: datetime,
    ) -> list[Measurement]:
        payload: dict[str, Any] = {
            "Locatie": {"Code": station_code},
            "AquoPlusWaarnemingMetadata": {
                "AquoMetadata": {
                    "Compartiment": {"Code": "OW"},
                    "Grootheid": {"Code": "WATHTE"},
                    "ProcesType": "meting",
                    "Hoedanigheid": {"Code": "NAP"},
                },
                "WaarnemingMetadata": {
                    "KwaliteitswaardecodeLijst": ["00", "10", "20", "25", "30", "40"]
                },
            },
            "Periode": {
                "Begindatumtijd": _rws_datetime(begin),
                "Einddatumtijd": _rws_datetime(end),
            },
        }
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
                    "begin": begin.isoformat(),
                    "end": end.isoformat(),
                },
                exc_info=exc,
            )
            message = "Rijkswaterstaat historical observations are unavailable"
            raise ExternalServiceError(message) from exc

        return _nap_water_level_measurements(parse_observations_response(response.json()))


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


def _nap_water_level_measurements(measurements: list[Measurement]) -> list[Measurement]:
    return [
        measurement
        for measurement in measurements
        if measurement.parameter == "water_level"
        and (measurement.source_metadata or {}).get("hoedanigheid") == "NAP"
    ]
