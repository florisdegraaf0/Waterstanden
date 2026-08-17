# Nederland Watermonitor

Modern interactive web app for exploring current Rijkswaterstaat water-level conditions across the Netherlands.

## What Is Included

- `frontend/`: Next.js, TypeScript, Tailwind CSS, MapLibre GL JS, Recharts.
- `backend/`: FastAPI backend with a Rijkswaterstaat DDAPI20 client boundary.
- `docker-compose.yml`: PostgreSQL/PostGIS, backend, and frontend.
- Initial PostGIS-ready schema for stations and measurements.

The first vertical slice loads real latest water-level station data from the current Rijkswaterstaat DDAPI20 WFS layer:

```text
https://geo.rijkswaterstaat.nl/services/ogc/hws/DDAPI20/ows
```

Recent station measurements are requested through the current DDAPI20 WaterWebservices observations endpoint:

```text
https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen
```

If that observations endpoint is temporarily unavailable, the backend returns a clearly marked fallback series for the chart while keeping the RWS client/service boundary intact.

## Run Locally

```bash
cp .env.example .env
docker compose up --build
```

Open:

```text
http://localhost:3000
```

Backend health check:

```text
http://localhost:8000/api/health
```

## Backend Development

```bash
cd backend
uv sync --dev
uv run pytest
uv run ruff check .
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Frontend Development

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run build
```

## API

- `GET /api/health`
- `GET /api/stations`
- `GET /api/stations/{station_id}`
- `GET /api/stations/{station_id}/measurements?hours=48`

The frontend receives normalized application models only. Rijkswaterstaat-specific response fields stay inside the backend client/service layer.

## Data Notes

- Latest stations are filtered to surface-water water-height observations: `COMPARTIMENTCODE=OW`, `GROOTHEIDCODE=WATHTE`.
- Source values in centimeters are normalized to meters for app responses.
- DDAPI20 WFS coordinates were observed as `POINT (latitude longitude)` and are mapped to app fields as `latitude` and `longitude`.
- The database schema is prepared for later historical ingestion, but the MVP reads live data directly from Rijkswaterstaat.
