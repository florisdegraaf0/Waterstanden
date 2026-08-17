import httpx
import pytest

import app.clients.rws.client as rws_client_module
from app.clients.rws.client import RwsClient
from app.config import Settings
from app.exceptions import ExternalServiceError


@pytest.mark.asyncio
async def test_latest_water_level_locations_are_filtered_at_wfs_boundary() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            text=(
                "CODE;NAAM;GROOTHEIDCODE;COMPARTIMENTCODE;KWALITEITSWAARDE_CODE;GEOMETRY;"
                "PARAMETER_WAT_OMSCHRIJVING\n"
                "station;Station;WATHTE;OW;00;POINT (52.0 5.0);Waterhoogte\n"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RwsClient(Settings(rws_wfs_base_url="https://example.test/ows"), http_client)

        observations = await client.fetch_latest_water_level_locations()

    assert len(observations) == 1
    assert captured_request is not None
    filter_param = captured_request.url.params["FILTER"]
    assert "<PropertyName>GROOTHEIDCODE</PropertyName>" in filter_param
    assert "<Literal>WATHTE</Literal>" in filter_param
    assert "<PropertyName>COMPARTIMENTCODE</PropertyName>" in filter_param
    assert "<Literal>OW</Literal>" in filter_param
    assert captured_request.url.params["MAXFEATURES"] == "1000"
    assert captured_request.url.params["PROPERTYNAME"] == (
        "CODE,NAAM,GEOMETRY,WAARDE_LAATSTE_METING,EENHEIDCODE,TIJDSTIP_LAATSTE_METING,"
        "PARAMETER_WAT_OMSCHRIJVING,STATUSWAARDE,KWALITEITSWAARDE_CODE,GROOTHEIDCODE,"
        "COMPARTIMENTCODE,HOEDANIGHEIDCODE"
    )


@pytest.mark.asyncio
async def test_latest_water_level_locations_rejects_oversized_wfs_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rws_client_module, "_MAX_WFS_RESPONSE_BYTES", 10)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="CODE;NAAM\nstation;Station\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = RwsClient(Settings(rws_wfs_base_url="https://example.test/ows"), http_client)

        with pytest.raises(ExternalServiceError):
            await client.fetch_latest_water_level_locations()
