"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { AlertCircle, Loader2 } from "lucide-react";

import {
  fetchMeasurements,
  fetchSeasonalContext,
  fetchStation,
  fetchStations,
  type MeasurementPoint,
  type SeasonalContext,
  type Station
} from "@/lib/api";
import { StationPanel } from "@/components/StationPanel";

export function WaterMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);

  const [stations, setStations] = useState<Station[]>([]);
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);
  const [measurements, setMeasurements] = useState<MeasurementPoint[]>([]);
  const [seasonalContext, setSeasonalContext] = useState<SeasonalContext | null>(null);
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

    fetchStations()
      .then((result) => {
        if (!cancelled) {
          setStations(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStationsError("Could not load Rijkswaterstaat stations.");
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

  useEffect(() => {
    if (!map.current) {
      return;
    }

    markers.current.forEach((marker) => marker.remove());
    markers.current = stations.map((station) => {
      const element = document.createElement("button");
      element.type = "button";
      element.className =
        "h-4 w-4 rounded-full border-2 border-white bg-water shadow-md ring-1 ring-slate-700/10 transition-transform hover:scale-125";
      element.setAttribute("aria-label", `Open ${station.name}`);
      element.addEventListener("click", () => selectStation(station.id));

      const marker = new maplibregl.Marker({ element })
        .setLngLat([station.longitude, station.latitude])
        .addTo(map.current as maplibregl.Map);

      return marker;
    });
  }, [stations]);

  async function selectStation(stationId: string) {
    const baseStation = stations.find((station) => station.id === stationId) ?? null;
    setSelectedStation(baseStation);
    setMeasurements([]);
    setSeasonalContext(null);
    setMeasurementsError(null);
    setMeasurementsLoading(true);

    try {
      const [station, stationMeasurements] = await Promise.all([
        fetchStation(stationId),
        fetchMeasurements(stationId, 48)
      ]);
      setSelectedStation(station);
      setMeasurements(stationMeasurements);
    } catch {
      setMeasurementsError("Recent measurements are temporarily unavailable.");
    } finally {
      setMeasurementsLoading(false);
    }

    fetchSeasonalContext(stationId)
      .then(setSeasonalContext)
      .catch(() => setSeasonalContext(null));
  }

  return (
    <main className="relative h-screen w-screen overflow-hidden">
      <div ref={mapContainer} className="h-full w-full" />

      <header className="absolute left-4 right-4 top-4 z-10 max-w-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur md:left-5 md:right-auto">
        <h1 className="text-base font-semibold text-ink md:text-lg">Nederland Watermonitor</h1>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
          <span>{stations.length} water level stations</span>
          {stationsLoading ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="animate-spin" size={14} />
              Loading RWS data
            </span>
          ) : null}
        </div>
      </header>

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
        loading={measurementsLoading}
        error={measurementsError}
        onClose={() => setSelectedStation(null)}
      />
    </main>
  );
}
