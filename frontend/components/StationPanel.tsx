"use client";

import { AlertCircle, Loader2, X } from "lucide-react";

import type { MeasurementPoint, SeasonalContext, SeasonalStatus, Station } from "@/lib/api";
import { WaterLevelChart } from "@/components/WaterLevelChart";

type Props = {
  station: Station | null;
  measurements: MeasurementPoint[];
  seasonalContext: SeasonalContext | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

export function StationPanel({
  station,
  measurements,
  seasonalContext,
  loading,
  error,
  onClose
}: Props) {
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

        <SeasonalSection context={seasonalContext} unit={station.unit} />

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

function SeasonalSection({ context, unit }: { context: SeasonalContext | null; unit: string | null }) {
  if (!context) {
    return (
      <section className="border-y border-slate-200 py-4">
        <div className="text-sm font-semibold text-ink">Seasonal context</div>
        <div className="mt-2 text-sm text-slate-500">Historical comparison is loading.</div>
      </section>
    );
  }

  const seasonal = context.seasonal_context;
  if (seasonal.status === "insufficient_data" && seasonal.sample_size === 0) {
    return (
      <section className="border-y border-slate-200 py-4">
        <div className="text-sm font-semibold text-ink">Seasonal context</div>
        <div className="mt-2 text-sm font-medium text-amber-700">
          No historical backfill data loaded.
        </div>
        <div className="mt-1 text-xs text-slate-500">
          Run the Lobith historical backfill to populate seasonal comparison.
        </div>
      </section>
    );
  }

  if (seasonal.status === "historical_data_unavailable") {
    return (
      <section className="border-y border-slate-200 py-4">
        <div className="text-sm font-semibold text-ink">Seasonal context</div>
        <div className="mt-2 text-sm font-medium text-amber-700">
          Historical comparison is unavailable.
        </div>
        <div className="mt-1 text-xs text-slate-500">
          The stored historical dataset could not be read.
        </div>
      </section>
    );
  }

  if (seasonal.status === "insufficient_data" || seasonal.percentile == null) {
    return (
      <section className="border-y border-slate-200 py-4">
        <div className="text-sm font-semibold text-ink">Seasonal context</div>
        <div className="mt-2 text-sm font-medium text-amber-700">Limited historical data available.</div>
        <div className="mt-1 text-xs text-slate-500">
          {seasonal.sample_size} daily values across {seasonal.years_used} years.
        </div>
      </section>
    );
  }

  return (
    <section className="border-y border-slate-200 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold text-ink">Seasonal context</div>
          <div className="mt-2 text-2xl font-semibold text-ink">
            {formatPercentile(seasonal.percentile)}
          </div>
          <div className="mt-1 text-sm text-slate-600">
            {statusLabel(seasonal.status)} for this time of year
          </div>
        </div>
        <div className="text-right text-xs text-slate-500">
          Compared with {seasonal.years_used} years
          <br />
          ±{seasonal.reference_period.window_days} days
        </div>
      </div>

      {seasonal.reference_values ? (
        <div className="mt-4">
          <div className="relative h-7">
            <div className="absolute left-0 right-0 top-3 h-1 bg-slate-200" />
            <div className="absolute left-[5%] right-[5%] top-3 h-1 bg-teal-500" />
            <div
              className="absolute top-0 h-7 w-0.5 bg-ink"
              style={{ left: `${Math.max(0, Math.min(100, seasonal.percentile))}%` }}
            />
          </div>
          <div className="mt-2 grid grid-cols-5 gap-2 text-xs text-slate-500">
            <StatLabel label="P05" value={seasonal.reference_values.p05} unit={unit} />
            <StatLabel label="P25" value={seasonal.reference_values.p25} unit={unit} />
            <StatLabel label="P50" value={seasonal.reference_values.p50} unit={unit} />
            <StatLabel label="P75" value={seasonal.reference_values.p75} unit={unit} />
            <StatLabel label="P95" value={seasonal.reference_values.p95} unit={unit} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function StatLabel({ label, value, unit }: { label: string; value: number; unit: string | null }) {
  return (
    <div>
      <div className="font-medium text-slate-700">{label}</div>
      <div>
        {value.toFixed(2)} {unit ?? "m"}
      </div>
    </div>
  );
}

function formatPercentile(value: number) {
  const rounded = Math.round(value);
  const suffix = rounded % 10 === 1 && rounded % 100 !== 11 ? "st" : rounded % 10 === 2 && rounded % 100 !== 12 ? "nd" : rounded % 10 === 3 && rounded % 100 !== 13 ? "rd" : "th";
  return `${rounded}${suffix} percentile`;
}

function statusLabel(status: SeasonalStatus) {
  const labels: Record<SeasonalStatus, string> = {
    extremely_low: "Extremely low",
    unusually_low: "Unusually low",
    normal: "Normal",
    unusually_high: "Unusually high",
    extremely_high: "Extremely high",
    insufficient_data: "Limited data",
    historical_data_unavailable: "Unavailable"
  };
  return labels[status];
}
