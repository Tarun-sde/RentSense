"use client";

import React, { useState } from "react";
import {
  Building2,
  Layers,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { AppShell } from "@/components/layout/AppShell";
import { GlassCard } from "@/components/ui/GlassCard";
import { MetricCard } from "@/components/ui/MetricCard";
import { TableSkeleton } from "@/components/ui/SkeletonLoader";
import { useApiQuery } from "@/lib/useApiQuery";
import { QueryError } from "@/components/ui/QueryError";
import { Forecast, Site } from "@/types";
import { cn } from "@/lib/utils";

export default function ForecastPage() {
  const [selectedSiteId, setSelectedSiteId] = useState<string>("ALL");
  const [selectedType, setSelectedType] = useState<string>("ALL");
  const [horizonWeeks, setHorizonWeeks] = useState<number>(4);
  const forecastQuery = useApiQuery<Forecast[]>(`/forecasts?horizon_weeks=${horizonWeeks}`);
  const sitesQuery = useApiQuery<Site[]>("/sites");
  const forecasts = forecastQuery.data ?? [];
  const sites = sitesQuery.data ?? [];
  const loading = forecastQuery.isPending;

  const filteredForecasts = forecasts.filter((f) => {
    const matchSite = selectedSiteId === "ALL" || f.site_id === selectedSiteId;
    const matchType = selectedType === "ALL" || f.equipment_type === selectedType;
    return matchSite && matchType;
  });

  // Calculate summary metrics
  const totalDemand = Math.round(
    filteredForecasts.reduce((acc, f) => acc + f.predicted_units, 0) * 10
  ) / 10;
  
  const avgConfidence = filteredForecasts.length > 0
    ? Math.round(
        (filteredForecasts.reduce((acc, f) => acc + f.confidence, 0) / filteredForecasts.length) * 100
      )
    : 0;

  const validErrors = filteredForecasts
    .map((f) => f.backtest_error)
    .filter((e): e is number => typeof e === "number");
  
  const avgMae = validErrors.length > 0
    ? Math.round((validErrors.reduce((acc, e) => acc + e, 0) / validErrors.length) * 100) / 100
    : 0;

  // Aggregate by week for chart visualization
  const weekMap: Record<string, { week: string; total: number; [key: string]: string | number }> = {};
  filteredForecasts.forEach((f) => {
    const weekLabel = `Week ${new Date(f.forecast_date).toLocaleDateString([], { month: "short", day: "numeric" })}`;
    if (!weekMap[weekLabel]) {
      weekMap[weekLabel] = { week: weekLabel, total: 0 };
    }
    const existingValue = weekMap[weekLabel][f.equipment_type];
    weekMap[weekLabel][f.equipment_type] = (typeof existingValue === "number" ? existingValue : 0) + f.predicted_units;
    weekMap[weekLabel].total += f.predicted_units;
  });
  const chartData = Object.values(weekMap);

  const equipmentTypes = Array.from(new Set(forecasts.map((f) => f.equipment_type)));

  return (
    <AppShell>
      <QueryError error={forecastQuery.error} retry={forecastQuery.refetch} />
      <QueryError error={sitesQuery.error} retry={sitesQuery.refetch} />
      {/* Page Header */}
      <section className="mb-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-black/10">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-2 bg-[#ff5a24] shadow-[0_0_0_1px_rgba(255,90,36,0.2)]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[#ff5a24]">
              Algorithmic Demand Projections
            </span>
          </div>
          <h1
            className="text-4xl sm:text-5xl font-medium tracking-tight text-black mt-1"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            Fleet Demand Forecast
          </h1>
          <p className="text-sm text-[#5a5a5a] mt-1.5 max-w-2xl">
            Deterministic weighted moving average demand modeling by jobsite and heavy equipment category with historical MAE backtesting.
          </p>
        </div>

        {/* Horizon selector */}
        <div className="flex items-center gap-2 rounded-xl border border-black/10 bg-white/70 p-1.5 shadow-sm text-xs">
          <span className="text-[#777] font-medium px-2">Horizon:</span>
          {[2, 4, 8].map((w) => (
            <button
              key={w}
              onClick={() => setHorizonWeeks(w)}
              className={cn(
                "px-3 py-1.5 rounded-lg font-medium transition-all",
                horizonWeeks === w
                  ? "bg-[#111111] text-white shadow-sm"
                  : "text-[#555] hover:text-black"
              )}
            >
              {w} Weeks
            </button>
          ))}
        </div>
      </section>

      {/* KPI Cards */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5 mb-10">
        <MetricCard
          title="Projected Demand"
          value={forecastQuery.data ? `${totalDemand} Units` : "—"}
          subtext="Aggregate fleet requirement"
          trend="WMA (0.5/0.3/0.2)"
          trendPositive={true}
          sparklineColor="#ff5a24"
          statusDotColor="bg-[#ff5a24]"
        />
        <MetricCard
          title="Model Confidence"
          value={filteredForecasts.length ? `${avgConfidence}%` : "—"}
          subtext="Deterministic stability score"
          trend="Calibrated"
          trendPositive={true}
          sparklineColor="#16a34a"
          statusDotColor="bg-emerald-500"
        />
        <MetricCard
          title="Backtest Error (MAE)"
          value={validErrors.length ? `±${avgMae} Units` : "—"}
          subtext="Historical mean absolute error"
          trend="Optimal Accuracy"
          trendPositive={true}
          sparklineColor="#2563eb"
          statusDotColor="bg-blue-500"
        />
        <MetricCard
          title="Monitored Sites"
          value={sitesQuery.data ? sites.length : "—"}
          subtext="Active bay infrastructure zones"
          trend="Full Surveillance"
          trendPositive={true}
          sparklineColor="#64748b"
          statusDotColor="bg-slate-400"
        />
      </section>

      {/* Filters & Projection Chart */}
      <section className="mb-10 space-y-6">
        {/* Site & Equipment Filter Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-black/10 bg-white/60 backdrop-blur shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-black uppercase tracking-wider flex items-center gap-1.5 mr-2">
              <Building2 className="size-3.5 text-[#ff5a24]" />
              Site:
            </span>
            <button
              onClick={() => setSelectedSiteId("ALL")}
              className={cn(
                "px-3 py-1.5 rounded-xl text-xs font-medium transition-all",
                selectedSiteId === "ALL"
                  ? "bg-[#111111] text-white shadow-sm"
                  : "bg-white/70 text-[#555] border border-black/10 hover:text-black"
              )}
            >
              All Sites
            </button>
            {sites.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedSiteId(s.id)}
                className={cn(
                  "px-3 py-1.5 rounded-xl text-xs font-medium transition-all",
                  selectedSiteId === s.id
                    ? "bg-[#111111] text-white shadow-sm"
                    : "bg-white/70 text-[#555] border border-black/10 hover:text-black"
                )}
              >
                {s.name}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-black uppercase tracking-wider flex items-center gap-1.5 mr-2">
              <Layers className="size-3.5 text-[#ff5a24]" />
              Type:
            </span>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="rounded-xl border border-black/10 bg-white px-3 py-1.5 text-xs font-medium text-black focus:outline-none focus:ring-1 focus:ring-[#ff5a24]"
            >
              <option value="ALL">All Categories</option>
              {equipmentTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Forecast Chart Card */}
        <GlassCard className="p-7">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Weekly Demand Projections
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">
                Weighted Moving Average unit demand distribution across forecast horizon
              </p>
            </div>
            <span className="text-xs font-mono text-[#ff5a24] bg-white px-3 py-1 rounded-full border border-black/10 shadow-xs">
              Model: WMA-V1.4
            </span>
          </div>

          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis dataKey="week" stroke="#888" fontSize={11} />
                <YAxis stroke="#888" fontSize={11} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111111",
                    borderRadius: "12px",
                    border: "1px solid rgba(255,255,255,0.2)",
                    color: "#ffffff",
                    fontSize: "12px",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                <Bar dataKey="Excavator" fill="#ff5a24" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Bulldozer" fill="#111111" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Wheel Loader" fill="#eab308" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Generator" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Scissor Lift" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Boom Lift" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </section>

      {/* Projections Table with Drivers */}
      <section className="mb-12">
        <GlassCard className="p-7">
          <div className="flex items-center justify-between pb-4 border-b border-black/10 mb-5">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Forecast Ledger &amp; Driver Signals
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">
                Explainable unit requirements with backtest verification
              </p>
            </div>
            <span className="text-xs font-mono text-[#7a7a7a]">
              {filteredForecasts.length} Projections
            </span>
          </div>

          {loading ? (
            <TableSkeleton />
          ) : filteredForecasts.length === 0 ? (
            <div className="py-12 text-center text-xs text-[#7a7a7a]">
              No forecasts matching the selected filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 text-[10px] uppercase font-bold text-[#666]">
                    <th className="pb-3">Site Location</th>
                    <th className="pb-3">Equipment Type</th>
                    <th className="pb-3">Period Date</th>
                    <th className="pb-3 text-right">Projected Demand</th>
                    <th className="pb-3 text-center">Confidence</th>
                    <th className="pb-3 text-center">Backtest MAE</th>
                    <th className="pb-3 pl-4">Driver &amp; Rationale</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5">
                  {filteredForecasts.map((f) => (
                    <tr key={f.id} className="hover:bg-black/[0.02] transition-colors">
                      <td className="py-3.5 font-semibold text-black">
                        {f.site_name || "Central Depot"}
                      </td>
                      <td className="py-3.5 text-[#444] font-medium">
                        {f.equipment_type}
                      </td>
                      <td className="py-3.5 text-[#666] font-mono">
                        {new Date(f.forecast_date).toLocaleDateString()}
                      </td>
                      <td className="py-3.5 text-right font-mono font-bold text-black text-sm">
                        {f.predicted_units.toFixed(1)} <span className="text-xs font-normal text-[#888]">units</span>
                      </td>
                      <td className="py-3.5 text-center">
                        <span
                          className={cn(
                            "px-2.5 py-0.5 rounded-full font-mono text-[10px] font-semibold border",
                            f.confidence >= 0.8
                              ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                              : "bg-amber-50 text-amber-700 border-amber-300"
                          )}
                        >
                          {Math.round(f.confidence * 100)}%
                        </span>
                      </td>
                      <td className="py-3.5 text-center font-mono text-[11px] text-[#666]">
                        {f.backtest_error !== null && f.backtest_error !== undefined
                          ? `±${f.backtest_error.toFixed(2)}`
                          : "N/A"}
                      </td>
                      <td className="py-3.5 pl-4 text-[#555] leading-snug max-w-md">
                        {f.explanation}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </GlassCard>
      </section>
    </AppShell>
  );
}
