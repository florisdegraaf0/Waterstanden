"use client";

import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { MeasurementPoint } from "@/lib/api";

type Props = {
  measurements: MeasurementPoint[];
};

export function WaterLevelChart({ measurements }: Props) {
  const data = measurements.map((point) => ({
    time: new Intl.DateTimeFormat("nl-NL", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit"
    }).format(new Date(point.measured_at)),
    value: point.value
  }));

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 8, bottom: 8, left: 0 }}>
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11, fill: "#5b6770" }}
            tickLine={false}
            axisLine={{ stroke: "#d7e0de" }}
            minTickGap={28}
          />
          <YAxis
            width={42}
            tick={{ fontSize: 11, fill: "#5b6770" }}
            tickLine={false}
            axisLine={{ stroke: "#d7e0de" }}
            domain={["dataMin - 0.1", "dataMax + 0.1"]}
          />
          <Tooltip
            formatter={(value) => [`${Number(value).toFixed(2)} m`, "Waterhoogte"]}
            labelClassName="text-xs text-slate-500"
            contentStyle={{ borderRadius: 6, borderColor: "#d7e0de" }}
          />
          <Line type="monotone" dataKey="value" stroke="#0f766e" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

