from collections.abc import AsyncIterator

from app.clients.rws.client import RwsClient
from app.config import Settings, get_settings


async def get_rws_client() -> AsyncIterator[RwsClient]:
    client = RwsClient(get_settings())
    try:
        yield client
    finally:
        await client.close()


def get_app_settings() -> Settings:
    return get_settings()
