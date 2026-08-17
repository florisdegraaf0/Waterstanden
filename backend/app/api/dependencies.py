from collections.abc import AsyncIterator, Iterator

from sqlalchemy.orm import Session

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


def get_db() -> Iterator[Session]:
    from app.db.session import get_db as session_get_db

    yield from session_get_db()


__all__ = ["get_app_settings", "get_db", "get_rws_client"]
