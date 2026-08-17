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
            "outputFormat": "csv",
            "format_options": "csvseparator:semicolon",
        }
        try:
            response = await self._client.get(self._settings.rws_wfs_base_url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("RWS WFS latest observations request failed", exc_info=exc)
            message = "Rijkswaterstaat latest observations are unavailable"
            raise ExternalServiceError(message) from exc

        return parse_latest_observations_csv(response.text)

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

        return parse_observations_response(response.json())


def _rws_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
