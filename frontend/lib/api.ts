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

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
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
