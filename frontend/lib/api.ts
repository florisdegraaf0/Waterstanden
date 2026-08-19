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
