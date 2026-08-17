"use client";

import { AlertCircle, Loader2, X } from "lucide-react";

import type { MeasurementPoint, Station } from "@/lib/api";
import { WaterLevelChart } from "@/components/WaterLevelChart";

type Props = {
  station: Station | null;
  measurements: MeasurementPoint[];
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

export function StationPanel({ station, measurements, loading, error, onClose }: Props) {
  if (!station) {
    return null;
  }

  const measuredAt = station.measured_at
    ? new Intl.DateTimeFormat("nl-NL", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(new Date(station.measured_at))
    : "Geen tijd beschikbaar";

  return (
    <aside className="absolute bottom-0 right-0 top-auto z-20 max-h-[72vh] w-full overflow-y-auto border-t border-slate-200 bg-white shadow-2xl md:bottom-5 md:right-5 md:top-5 md:max-h-none md:w-[390px] md:border md:shadow-xl">
      <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">{station.name}</h2>
          <p className="mt-1 text-sm text-slate-500">{station.id}</p>
        </div>
        <button
          aria-label="Close station panel"
          className="rounded border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
          onClick={onClose}
          type="button"
        >
          <X size={18} />
        </button>
      </div>

      <div className="space-y-5 px-5 py-5">
        <div>
          <div className="text-sm text-slate-500">Current water level</div>
          <div className="mt-1 flex items-end gap-2">
            <span className="text-4xl font-semibold tracking-normal text-ink">
              {station.latest_value == null ? "n/a" : station.latest_value.toFixed(2)}
            </span>
            {station.unit ? (
              <span className="pb-1 text-sm font-medium text-slate-500">{station.unit}</span>
            ) : null}
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-slate-500">Measured</dt>
            <dd className="mt-1 font-medium text-ink">{measuredAt}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Status</dt>
            <dd className="mt-1 font-medium text-ink">{station.status ?? "Unknown"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Latitude</dt>
            <dd className="mt-1 font-medium text-ink">{station.latitude.toFixed(5)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Longitude</dt>
            <dd className="mt-1 font-medium text-ink">{station.longitude.toFixed(5)}</dd>
          </div>
        </dl>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">Last 48 hours</h3>
            {loading ? <Loader2 className="animate-spin text-slate-400" size={16} /> : null}
          </div>
          {error ? (
            <div className="flex gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <AlertCircle className="mt-0.5 shrink-0" size={16} />
              <span>{error}</span>
            </div>
          ) : measurements.length > 0 ? (
            <WaterLevelChart measurements={measurements} />
          ) : (
            <div className="rounded border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
              No recent measurements available.
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}

