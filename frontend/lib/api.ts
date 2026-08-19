const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Station = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  latest_value: number | null;
  unit: string | null;
  measured_at: string | null;
  parameter: string;
  status: string | null;
  quality_code: string | null;
  metadata?: Record<string, string | number | null>;
};

export type MeasurementPoint = {
  measured_at: string;
  value: number;
  unit: string;
  parameter: string;
  quality_code: string | null;
};

export type SeasonalStatus =
  | "extremely_low"
  | "unusually_low"
  | "normal"
  | "unusually_high"
  | "extremely_high"
  | "insufficient_data"
  | "historical_data_unavailable";

export type SeasonalContext = {
  station_id: string;
  parameter: string;
  current: {
    value: number | null;
    unit: string | null;
    measured_at: string | null;
  };
  seasonal_context: {
    percentile: number | null;
    status: SeasonalStatus;
    sample_size: number;
    years_used: number;
    historical_sample_size: number;
    historical_years: number;
    reference_period: {
      window_days: number;
      first_year: number | null;
      last_year: number | null;
    };
    reference_values: {
      p05: number;
      p25: number;
      p50: number;
      p75: number;
      p95: number;
    } | null;
  };
};

export type AnomalySignal = {
  type: string;
  category: "hydrological" | "data_quality";
  score: number | null;
  direction: string | null;
  value: number | null;
  unit: string | null;
  percentile: number | null;
  message: string;
};

export type StationAnomaly = {
  station_id: string;
  parameter: string;
  evaluated_at: string;
  current: {
    value: number | null;
    unit: string | null;
    measured_at: string | null;
  };
  anomaly: {
    status: "ok" | "insufficient_data" | "data_quality_anomaly" | "historical_data_unavailable";
    score: number | null;
    severity: "normal" | "low" | "moderate" | "high" | "extreme";
    is_anomalous: boolean;
    confidence: "low" | "medium" | "high";
    signals: AnomalySignal[];
  };
  data_quality: {
    status: "normal" | "degraded" | "data_quality_anomaly";
    signals: AnomalySignal[];
    historical_years: number;
    historical_sample_size: number;
    recent_measurement_count: number;
    largest_recent_gap_minutes: number | null;
  };
};

export type OverviewFilter =
  | "all"
  | "high_extreme"
  | "unusually_high"
  | "unusually_low"
  | "rapidly_rising"
  | "rapidly_falling";

export type OverviewSort =
  | "anomaly_score"
  | "largest_24h_rise"
  | "largest_24h_fall"
  | "seasonal_unusualness";

export type OverviewPrimarySignal = {
  type: string;
  direction: string | null;
  value: number | null;
  unit: string | null;
  percentile: number | null;
  score: number | null;
  message: string;
};

export type OverviewStation = {
  station_id: string;
  station_name: string;
  water_system: string;
  latitude: number;
  longitude: number;
  current_value: number | null;
  unit: string | null;
  measured_at: string | null;
  parameter: string;
  seasonal_percentile: number | null;
  seasonal_status: SeasonalStatus;
  anomaly_score: number | null;
  anomaly_severity: StationAnomaly["anomaly"]["severity"];
  anomaly_status: StationAnomaly["anomaly"]["status"];
  anomaly_direction: string | null;
  confidence: StationAnomaly["anomaly"]["confidence"];
  data_quality_status: StationAnomaly["data_quality"]["status"];
  freshness_status: "current" | "stale";
  delta_24h: number | null;
  primary_signal: OverviewPrimarySignal | null;
};

export type Overview = {
  generated_at: string;
  summary: {
    stations_monitored: number;
    high_or_extreme_anomalies: number;
    extreme_anomalies: number;
    rapidly_rising: number;
    rapidly_falling: number;
    data_limited_or_stale: number;
  };
  coverage: {
    historical_context_stations: number;
    insufficient_data_stations: number;
    stale_stations: number;
    rankable_stations: number;
  };
  stations: OverviewStation[];
};

async function fetchJson<T>(path: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Network request failed";
    throw new Error(`Could not reach API at ${url}: ${detail}`);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new Error(`API request failed: ${response.status} ${detail}`);
  }

  return response.json() as Promise<T>;
}

export function fetchStations(): Promise<Station[]> {
  return fetchJson<Station[]>("/api/stations");
}

export function fetchStation(stationId: string): Promise<Station> {
  return fetchJson<Station>(`/api/stations/${encodeURIComponent(stationId)}`);
}

export function fetchMeasurements(stationId: string, hours: number): Promise<MeasurementPoint[]> {
  const params = new URLSearchParams({ hours: String(hours) });
  return fetchJson<MeasurementPoint[]>(
    `/api/stations/${encodeURIComponent(stationId)}/measurements?${params}`
  );
}

export function fetchSeasonalContext(station: Station): Promise<SeasonalContext> {
  const params = new URLSearchParams({ parameter: "water_level" });
  if (station.latest_value != null) {
    params.set("current_value", String(station.latest_value));
  }
  if (station.unit) {
    params.set("current_unit", station.unit);
  }
  if (station.measured_at) {
    params.set("measured_at", station.measured_at);
  }
  return fetchJson<SeasonalContext>(
    `/api/stations/${encodeURIComponent(station.id)}/seasonal-context?${params}`
  );
}

export function fetchStationAnomaly(station: Station): Promise<StationAnomaly> {
  const params = new URLSearchParams({ parameter: "water_level" });
  return fetchJson<StationAnomaly>(
    `/api/stations/${encodeURIComponent(station.id)}/anomaly?${params}`
  );
}

export function fetchOverview(options: {
  filter: OverviewFilter;
  sort: OverviewSort;
  limit?: number;
}): Promise<Overview> {
  const params = new URLSearchParams({
    parameter: "water_level",
    filter: options.filter,
    sort: options.sort,
    limit: String(options.limit ?? 50)
  });
  return fetchJson<Overview>(`/api/overview?${params}`);
}
