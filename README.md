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
- `GET /api/stations/{station_id}/seasonal-context?parameter=water_level`
- `GET /api/stations/{station_id}/anomaly?parameter=water_level`
- `GET /api/overview?parameter=water_level&filter=all&sort=anomaly_score&limit=50`

The frontend receives normalized application models only. Rijkswaterstaat-specific response fields stay inside the backend client/service layer.

## Historical Seasonal Percentiles

The first historical percentile slice targets Lobith water level at:

```text
lobith.bovenrijn.tolkamer
```

Backfill historical observations before expecting a seasonal percentile:

```bash
cd backend
uv run alembic upgrade head
uv run python -m app.jobs.backfill_station \
  --station-id lobith.bovenrijn.tolkamer \
  --parameter water_level \
  --from 2010-01-01 \
  --to 2025-12-31
```

The job is idempotent: it upserts raw normalized measurements and recomputes daily statistics for each chunk. Percentiles compare the current 24-hour mean with historical daily means in a configurable ±14 day seasonal window, excluding the current year.

To keep the persisted station list limited to currently active stations, run:

```bash
cd backend
uv run python -m app.jobs.sync_active_stations --active-max-age-hours 24
```

## Data Notes

- Latest stations are filtered to surface-water water-height observations: `COMPARTIMENTCODE=OW`, `GROOTHEIDCODE=WATHTE`.
- Source values in centimeters are normalized to meters for app responses.
- DDAPI20 WFS coordinates were observed as `POINT (latitude longitude)` and are mapped to app fields as `latitude` and `longitude`.
- Historical percentile context is read from persisted backfill data and daily aggregates. Live station lists and current values still come directly from Rijkswaterstaat.

## Anomaly Detection

The first anomaly-detection slice is statistical and explainable. For a selected
station, the backend compares the current water level and 24-hour change with
station-specific seasonal historical references.

The anomaly score is unusualness, not danger or flood probability:

```text
component_score = abs(percentile - 50) * 2
overall_score = 0.55 * seasonal_level_score + 0.45 * 24h_change_score
```

Both high and low extremes are treated symmetrically. A 99th percentile and a
1st percentile both produce a strong component score.

Historical 24-hour change references are stored as one derived daily value per
station, parameter, date, and window. The value is calculated from daily means:

```text
24h delta for day D = daily_mean(D) - daily_mean(D - 1)
```

This avoids giving extra statistical weight to stations or periods with more
frequent observations. The same ±14 day seasonal window used for seasonal
percentiles is used for 24-hour change comparisons.

The backend returns structured explanatory signals, severity, confidence, and
data-quality metadata through:

```text
GET /api/stations/{station_id}/anomaly
```

If recent data looks unreliable, for example stale measurements, fallback values,
duplicate timestamps, flatlining, or an isolated spike, the response marks this
as a data-quality anomaly and suppresses hydrological scoring.

## Netherlands Overview

The overview screen at `/overview` answers "What's unusual today?" with one
overview API request rather than one anomaly request per station.

The default ranking uses the cached station anomaly score, descending. This is
preferred over raw seasonal percentile because the anomaly score is two-sided and
can combine unusual absolute levels with unusual 24-hour movement. A 1st
percentile and a 99th percentile are therefore treated as equally unusual before
the 24-hour movement component is applied.

Overview snapshots are persisted in `station_overview_snapshots` and are lazily
refreshed by `GET /api/overview` when older than `OVERVIEW_CACHE_TTL_MINUTES`
(default: 15). A refresh fetches the active station list once, fetches recent
measurements with bounded concurrency, and reads historical daily and 24-hour
change statistics in batch. Stale or data-quality-suppressed stations are
excluded from the main ranked list and counted in the coverage summary.
