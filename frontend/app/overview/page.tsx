"use client";

import Link from "next/link";
import { AlertCircle, ArrowDown, ArrowUp, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchOverview,
  type Overview,
  type OverviewFilter,
  type OverviewSort,
  type OverviewStation
} from "@/lib/api";

const FILTERS: { value: OverviewFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "high_extreme", label: "High / extreme" },
  { value: "unusually_high", label: "Unusually high" },
  { value: "unusually_low", label: "Unusually low" },
  { value: "rapidly_rising", label: "Rapidly rising" },
  { value: "rapidly_falling", label: "Rapidly falling" }
];

const SORTS: { value: OverviewSort; label: string }[] = [
  { value: "anomaly_score", label: "Most unusual" },
  { value: "largest_24h_rise", label: "Largest 24h rise" },
  { value: "largest_24h_fall", label: "Largest 24h fall" },
  { value: "seasonal_unusualness", label: "Seasonal unusualness" }
];

export default function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [filter, setFilter] = useState<OverviewFilter>("all");
  const [sort, setSort] = useState<OverviewSort>("anomaly_score");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchOverview({ filter, sort, limit: 50 })
      .then((result) => {
        if (!cancelled) {
          setOverview(result);
        }
      })
      .catch((apiError: unknown) => {
        if (!cancelled) {
          const detail = apiError instanceof Error ? apiError.message : "Unknown error";
          setError(`Unable to load the national overview. ${detail}`);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [filter, sort]);

  return (
    <main className="min-h-screen bg-[#eef4f3] text-ink">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-medium text-teal-700">Nederland Watermonitor</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal text-ink">
              What&apos;s unusual today?
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {overview ? `Updated ${formatDateTime(overview.generated_at)}` : "Loading overview"}
            </p>
          </div>
          <nav className="flex gap-2 text-sm font-medium">
            <Link className="border border-slate-200 px-3 py-2 text-slate-600 hover:bg-slate-50" href="/">
              Map
            </Link>
            <Link className="border border-teal-700 bg-teal-700 px-3 py-2 text-white" href="/overview">
              Overview
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-6">
        {overview ? <Summary overview={overview} /> : <SummaryLoading />}

        <section className="mt-6">
          <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-ink">Most unusual stations</h2>
              {overview ? (
                <p className="mt-1 text-sm text-slate-500">
                  Historical context is available for{" "}
                  {overview.coverage.historical_context_stations} of{" "}
                  {overview.summary.stations_monitored} active stations.
                </p>
              ) : null}
            </div>

            <div className="flex flex-col gap-3 md:flex-row">
              <label className="text-sm font-medium text-slate-600">
                Filter
                <select
                  className="mt-1 block w-full border border-slate-300 bg-white px-3 py-2 text-sm text-ink"
                  onChange={(event) => setFilter(event.target.value as OverviewFilter)}
                  value={filter}
                >
                  {FILTERS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium text-slate-600">
                Sort
                <select
                  className="mt-1 block w-full border border-slate-300 bg-white px-3 py-2 text-sm text-ink"
                  onChange={(event) => setSort(event.target.value as OverviewSort)}
                  value={sort}
                >
                  {SORTS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {loading ? (
            <div className="mt-8 flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="animate-spin" size={16} />
              Loading national overview
            </div>
          ) : error ? (
            <div className="mt-8 flex gap-2 border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
              <AlertCircle className="mt-0.5 shrink-0" size={16} />
              <span>{error}</span>
            </div>
          ) : overview && overview.stations.length > 0 ? (
            <div className="mt-4 divide-y divide-slate-200 border-y border-slate-200 bg-white">
              {overview.stations.map((station, index) => (
                <StationRow key={station.station_id} rank={index + 1} station={station} />
              ))}
            </div>
          ) : (
            <div className="mt-8 border border-slate-200 bg-white p-5">
              <h3 className="font-semibold text-ink">Nothing particularly unusual right now.</h3>
              <p className="mt-1 text-sm text-slate-500">
                Most monitored stations are within their typical seasonal ranges, or there is not
                enough fresh historical context for this filter.
              </p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function Summary({ overview }: { overview: Overview }) {
  const items = [
    { label: "Stations monitored", value: overview.summary.stations_monitored },
    { label: "High / extreme", value: overview.summary.high_or_extreme_anomalies },
    { label: "Extremely unusual", value: overview.summary.extreme_anomalies },
    { label: "Rapid movement", value: overview.summary.rapidly_rising + overview.summary.rapidly_falling },
    { label: "Limited or stale", value: overview.summary.data_limited_or_stale }
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="border border-slate-200 bg-white p-4">
          <div className="text-2xl font-semibold text-ink">{item.value}</div>
          <div className="mt-1 text-sm text-slate-500">{item.label}</div>
        </div>
      ))}
    </section>
  );
}

function SummaryLoading() {
  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {["Stations monitored", "High / extreme", "Extremely unusual", "Rapid movement", "Limited or stale"].map(
        (label) => (
          <div key={label} className="border border-slate-200 bg-white p-4">
            <div className="h-8 w-12 bg-slate-100" />
            <div className="mt-2 text-sm text-slate-400">{label}</div>
          </div>
        )
      )}
    </section>
  );
}

function StationRow({ station, rank }: { station: OverviewStation; rank: number }) {
  const mapHref = `/?station=${encodeURIComponent(station.station_id)}`;
  return (
    <Link className="block p-4 hover:bg-slate-50" href={mapHref}>
      <div className="grid gap-4 md:grid-cols-[48px_1fr_auto] md:items-start">
        <div className="text-xl font-semibold text-slate-400">#{rank}</div>
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="text-lg font-semibold text-ink">{station.station_name}</h3>
            <span className="text-sm text-slate-500">{station.water_system}</span>
          </div>
          <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
            <Metric label="Current" value={formatValue(station.current_value, station.unit)} />
            <Metric label="Seasonal" value={formatPercentile(station.seasonal_percentile)} />
            <Metric label="Movement" value={formatDelta(station.delta_24h)} />
          </div>
          {station.primary_signal ? (
            <p className="mt-3 max-w-3xl text-sm text-slate-600">{station.primary_signal.message}</p>
          ) : null}
          <p className="mt-2 text-xs text-slate-500">
            Measured {station.measured_at ? formatDateTime(station.measured_at) : "unknown"}
            {station.confidence !== "high" ? ` · ${station.confidence} confidence` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3 md:block md:text-right">
          <div className="text-2xl font-semibold text-ink">
            {station.anomaly_score == null ? "n/a" : station.anomaly_score}
          </div>
          <div className={`mt-1 inline-flex items-center gap-1 text-sm font-medium ${severityClass(station.anomaly_severity)}`}>
            {directionIcon(station.anomaly_direction)}
            {severityLabel(station.anomaly_severity)}
          </div>
        </div>
      </div>
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase text-slate-400">{label}</div>
      <div className="mt-1 font-medium text-ink">{value}</div>
    </div>
  );
}

function directionIcon(direction: string | null) {
  if (direction === "high" || direction === "rising") {
    return <ArrowUp size={15} />;
  }
  if (direction === "low" || direction === "falling") {
    return <ArrowDown size={15} />;
  }
  return null;
}

function formatValue(value: number | null, unit: string | null) {
  if (value == null) {
    return "n/a";
  }
  return `${value.toFixed(2)} ${unit ?? "m"}`;
}

function formatPercentile(value: number | null) {
  if (value == null) {
    return "Limited data";
  }
  return `${Math.round(value)}th percentile`;
}

function formatDelta(value: number | null) {
  if (value == null) {
    return "n/a";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value * 100)} cm / 24h`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("nl-NL", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function severityLabel(severity: OverviewStation["anomaly_severity"]) {
  const labels: Record<OverviewStation["anomaly_severity"], string> = {
    normal: "Normal",
    low: "Low",
    moderate: "Moderate",
    high: "High",
    extreme: "Extreme"
  };
  return labels[severity];
}

function severityClass(severity: OverviewStation["anomaly_severity"]) {
  const classes: Record<OverviewStation["anomaly_severity"], string> = {
    normal: "text-slate-500",
    low: "text-sky-700",
    moderate: "text-amber-700",
    high: "text-orange-700",
    extreme: "text-rose-700"
  };
  return classes[severity];
}
