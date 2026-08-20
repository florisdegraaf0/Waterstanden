"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { AlertCircle, ArrowDown, ArrowUp, Loader2 } from "lucide-react";

import {
  fetchMeasurements,
  fetchMapStations,
  fetchSeasonalContext,
  fetchStationAnomaly,
  fetchStation,
  type MapStation,
  type MeasurementPoint,
  type SeasonalContext,
  type StationAnomaly,
  type Station
} from "@/lib/api";
import { StationPanel } from "@/components/StationPanel";

export function WaterMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const hoverPopup = useRef<maplibregl.Popup | null>(null);
  const initialStationSelected = useRef(false);

  const [stations, setStations] = useState<MapStation[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("all");
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);
  const [selectedParameter, setSelectedParameter] = useState("water_level");
  const [measurements, setMeasurements] = useState<MeasurementPoint[]>([]);
  const [seasonalContext, setSeasonalContext] = useState<SeasonalContext | null>(null);
  const [anomaly, setAnomaly] = useState<StationAnomaly | null>(null);
  const [stationsLoading, setStationsLoading] = useState(true);
  const [stationsError, setStationsError] = useState<string | null>(null);
  const [measurementsLoading, setMeasurementsLoading] = useState(false);
  const [measurementsError, setMeasurementsError] = useState<string | null>(null);

  useEffect(() => {
    if (!mapContainer.current || map.current) {
      return;
    }

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      center: [5.3, 52.15],
      zoom: 7,
      attributionControl: false
    });
    map.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    map.current.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStationsLoading(true);
    setStationsError(null);

    fetchMapStations()
      .then((result) => {
        if (!cancelled) {
          setStations(result);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const detail = error instanceof Error ? error.message : "Unknown error";
          setStationsError(`Could not load Rijkswaterstaat stations. ${detail}`);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setStationsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const selectStation = useCallback(async (stationId: string) => {
    const baseStation = stations.find((station) => station.id === stationId) ?? null;
    setSelectedStation(baseStation);
    setSelectedParameter("water_level");
    setMeasurements([]);
    setSeasonalContext(null);
    setAnomaly(null);
    setMeasurementsError(null);
    setMeasurementsLoading(true);

    try {
      const station = await fetchStation(stationId);
      const parameter = defaultParameter(station);
      const stationMeasurements = await fetchMeasurements(stationId, 48, parameter);
      setSelectedStation(station);
      setSelectedParameter(parameter);
      setMeasurements(stationMeasurements);
      fetchSeasonalContext(station, parameter)
        .then(setSeasonalContext)
        .catch(() => setSeasonalContext(null));
      fetchStationAnomaly(station, parameter)
        .then(setAnomaly)
        .catch(() => setAnomaly(null));
    } catch {
      setMeasurementsError("Recent measurements are temporarily unavailable.");
    } finally {
      setMeasurementsLoading(false);
    }
  }, [stations]);

  const selectParameter = useCallback(async (parameter: string) => {
    if (!selectedStation) {
      return;
    }
    setSelectedParameter(parameter);
    setMeasurements([]);
    setSeasonalContext(null);
    setAnomaly(null);
    setMeasurementsError(null);
    setMeasurementsLoading(true);
    try {
      const stationMeasurements = await fetchMeasurements(selectedStation.id, 48, parameter);
      setMeasurements(stationMeasurements);
      fetchSeasonalContext(selectedStation, parameter)
        .then(setSeasonalContext)
        .catch(() => setSeasonalContext(null));
      fetchStationAnomaly(selectedStation, parameter)
        .then(setAnomaly)
        .catch(() => setAnomaly(null));
    } catch {
      setMeasurementsError("Recent measurements are temporarily unavailable.");
    } finally {
      setMeasurementsLoading(false);
    }
  }, [selectedStation]);

  const stationGroups = stationGroupOptions(stations);
  const filteredStations = stations.filter((station) => {
    return selectedGroup === "all" || station.station_group === selectedGroup;
  });

  useEffect(() => {
    if (
      selectedStation &&
      selectedGroup !== "all" &&
      selectedStation.station_group !== selectedGroup
    ) {
      setSelectedStation(null);
    }
  }, [selectedGroup, selectedStation]);

  useEffect(() => {
    if (!map.current) {
      return;
    }

    markers.current.forEach((marker) => marker.remove());
    markers.current = filteredStations.map((station) => {
      const isSelected = selectedStation?.id === station.id;
      const element = document.createElement("button");
      element.type = "button";
      element.className = markerClassName(isSelected);
      element.style.backgroundColor = severityColor(station);
      element.style.zIndex = isSelected ? "20" : "1";
      element.innerHTML = directionGlyph(station.anomaly_direction);
      element.setAttribute("aria-label", markerAriaLabel(station));
      element.addEventListener("click", () => selectStation(station.id));
      element.addEventListener("mouseenter", () => {
        hoverPopup.current?.remove();
        hoverPopup.current = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 14
        })
          .setLngLat([station.longitude, station.latitude])
          .setHTML(tooltipHtml(station))
          .addTo(map.current as maplibregl.Map);
      });
      element.addEventListener("mouseleave", () => {
        hoverPopup.current?.remove();
        hoverPopup.current = null;
      });

      const marker = new maplibregl.Marker({ element })
        .setLngLat([station.longitude, station.latitude])
        .addTo(map.current as maplibregl.Map);

      return marker;
    });
  }, [filteredStations, selectStation, selectedStation]);

  useEffect(() => {
    if (initialStationSelected.current || stations.length === 0) {
      return;
    }
    const stationId = new URLSearchParams(window.location.search).get("station");
    if (!stationId) {
      return;
    }
    initialStationSelected.current = true;
    void selectStation(stationId);
  }, [selectStation, stations.length]);

  return (
    <main className="relative h-screen w-screen overflow-hidden">
      <div ref={mapContainer} className="h-full w-full" />

      <header className="absolute left-4 right-4 top-4 z-10 max-w-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur md:left-5 md:right-auto">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-base font-semibold text-ink md:text-lg">Nederland Watermonitor</h1>
          <nav className="flex gap-2 text-xs font-medium">
            <Link className="border border-teal-700 bg-teal-700 px-2 py-1 text-white" href="/">
              Map
            </Link>
            <Link className="border border-slate-200 px-2 py-1 text-slate-600 hover:bg-slate-50" href="/overview">
              Overview
            </Link>
          </nav>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
          <span>
            {filteredStations.length} of {stations.length} water level stations
          </span>
          {stationsLoading ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="animate-spin" size={14} />
              Loading RWS data
            </span>
          ) : null}
        </div>
        {stationGroups.length > 1 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {stationGroups.map((group) => (
              <button
                className={`border px-2 py-1 text-xs font-medium ${
                  selectedGroup === group.value
                    ? "border-teal-700 bg-teal-700 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
                key={group.value}
                onClick={() => setSelectedGroup(group.value)}
                type="button"
              >
                {group.label} ({group.count})
              </button>
            ))}
          </div>
        ) : null}
      </header>

      <MapLegend />

      {stationsError ? (
        <div className="absolute left-4 right-4 top-24 z-10 max-w-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 shadow md:left-5 md:right-auto">
          <div className="flex gap-2">
            <AlertCircle className="mt-0.5 shrink-0" size={16} />
            <span>{stationsError}</span>
          </div>
        </div>
      ) : null}

      <StationPanel
        station={selectedStation}
        measurements={measurements}
        seasonalContext={seasonalContext}
        anomaly={anomaly}
        selectedParameter={selectedParameter}
        loading={measurementsLoading}
        error={measurementsError}
        onSelectParameter={selectParameter}
        onClose={() => setSelectedStation(null)}
      />
    </main>
  );
}

type StationGroupOption = {
  value: string;
  label: string;
  count: number;
};

const SEVERITY_COLORS: Record<MapStation["anomaly_severity"], string> = {
  normal: "#64748b",
  low: "#0ea5e9",
  moderate: "#d97706",
  high: "#ea580c",
  extreme: "#e11d48"
};

function stationGroupOptions(stations: MapStation[]): StationGroupOption[] {
  const byGroup = new Map<string, StationGroupOption>();
  for (const station of stations) {
    const value = station.station_group ?? "other";
    const label = station.station_group_label ?? "Other";
    const current = byGroup.get(value);
    byGroup.set(value, {
      value,
      label,
      count: (current?.count ?? 0) + 1
    });
  }
  const groups = [...byGroup.values()].sort((a, b) => a.label.localeCompare(b.label));
  return [{ value: "all", label: "All", count: stations.length }, ...groups];
}

function defaultParameter(station: Station) {
  if (station.available_parameters.includes("water_level")) {
    return "water_level";
  }
  return station.available_parameters[0] ?? "water_level";
}

function markerClassName(isSelected: boolean) {
  const base =
    "flex h-5 w-5 items-center justify-center rounded-full border-2 text-[10px] font-bold leading-none text-white shadow-md transition-transform hover:scale-125 focus:outline-none focus:ring-2 focus:ring-ink focus:ring-offset-2";
  if (!isSelected) {
    return `${base} border-white ring-1 ring-slate-700/20`;
  }
  return `${base} scale-125 border-white ring-4 ring-ink/70 ring-offset-2 ring-offset-white`;
}

function severityColor(station: MapStation) {
  if (station.freshness_status === "stale" || station.anomaly_status === "insufficient_data") {
    return "#94a3b8";
  }
  return SEVERITY_COLORS[station.anomaly_severity] ?? SEVERITY_COLORS.normal;
}

function directionGlyph(direction: string | null) {
  if (direction === "high" || direction === "rising") {
    return "↑";
  }
  if (direction === "low" || direction === "falling") {
    return "↓";
  }
  return "";
}

function markerAriaLabel(station: MapStation) {
  const severity = severityLabel(station.anomaly_severity);
  const percentile = formatPercentile(station.seasonal_percentile);
  return `Open ${station.name}, ${station.water_system ?? "unknown water system"}, ${severity}, ${percentile}`;
}

function tooltipHtml(station: MapStation) {
  const direction = directionLabel(station.anomaly_direction);
  return [
    `<div class="text-sm font-semibold text-ink">${escapeHtml(station.name)}</div>`,
    `<div class="mt-0.5 text-xs text-slate-500">${escapeHtml(station.water_system ?? "Unknown water system")}</div>`,
    `<div class="mt-2 text-xs text-slate-600">Anomaly: ${formatScore(station.anomaly_score)} · ${severityLabel(station.anomaly_severity)}</div>`,
    `<div class="text-xs text-slate-600">${formatPercentile(station.seasonal_percentile)}${direction ? ` · ${direction}` : ""}</div>`
  ].join("");
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatScore(value: number | null) {
  return value == null ? "n/a" : String(value);
}

function formatPercentile(value: number | null) {
  return value == null ? "Limited data" : `${Math.round(value)}th percentile`;
}

function severityLabel(severity: MapStation["anomaly_severity"]) {
  const labels: Record<MapStation["anomaly_severity"], string> = {
    normal: "Normal",
    low: "Low",
    moderate: "Moderate",
    high: "High",
    extreme: "Extreme"
  };
  return labels[severity];
}

function directionLabel(direction: string | null) {
  if (direction === "high") {
    return "↑ unusually high";
  }
  if (direction === "low") {
    return "↓ unusually low";
  }
  if (direction === "rising") {
    return "↑ rising fast";
  }
  if (direction === "falling") {
    return "↓ falling fast";
  }
  return null;
}

function MapLegend() {
  const items: Array<{ label: string; severity: MapStation["anomaly_severity"] }> = [
    { label: "Normal", severity: "normal" },
    { label: "Moderate", severity: "moderate" },
    { label: "High", severity: "high" },
    { label: "Extreme", severity: "extreme" }
  ];
  return (
    <aside className="absolute bottom-20 left-4 z-10 border border-slate-200 bg-white/95 px-3 py-2 text-xs text-slate-600 shadow-lg backdrop-blur md:bottom-20 md:left-5">
      <div className="font-semibold text-ink">Anomaly</div>
      <div className="mt-2 grid gap-1">
        {items.map((item) => (
          <div className="flex items-center gap-2" key={item.severity}>
            <span
              className="h-3 w-3 rounded-full border border-white shadow ring-1 ring-slate-700/20"
              style={{ backgroundColor: SEVERITY_COLORS[item.severity] }}
            />
            <span>{item.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-3 border-t border-slate-200 pt-2">
        <span className="inline-flex items-center gap-1">
          <ArrowUp size={12} /> high
        </span>
        <span className="inline-flex items-center gap-1">
          <ArrowDown size={12} /> low
        </span>
      </div>
    </aside>
  );
}
