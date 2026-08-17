from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.exceptions import ExternalDataError, ExternalServiceError, StationNotFound
from app.logging import configure_logging

settings = get_settings()
configure_logging(settings)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(StationNotFound)
async def station_not_found_handler(_request: Request, exc: StationNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ExternalServiceError)
async def external_service_handler(_request: Request, exc: ExternalServiceError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ExternalDataError)
async def external_data_handler(_request: Request, exc: ExternalDataError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
