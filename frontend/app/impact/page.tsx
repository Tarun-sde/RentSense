"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  DollarSign,
  Building2,
  ArrowUpRight,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { AppShell } from "@/components/layout/AppShell";
import { GlassCard } from "@/components/ui/GlassCard";
import { MetricCard } from "@/components/ui/MetricCard";
import { TableSkeleton } from "@/components/ui/SkeletonLoader";
import { useApiQuery } from "@/lib/useApiQuery";
import { QueryError } from "@/components/ui/QueryError";
import { ImpactSummary, Site } from "@/types";
import { cn, formatCurrency } from "@/lib/utils";

export default function ImpactPage() {
  const [selectedSiteId, setSelectedSiteId] = useState<string>("ALL");
  const impactQuery = useApiQuery<ImpactSummary>(`/impact${selectedSiteId === "ALL" ? "" : `?site_id=${encodeURIComponent(selectedSiteId)}`}`);
  const sitesQuery = useApiQuery<Site[]>("/sites");
  const summary = impactQuery.data;
  const sites = sitesQuery.data ?? [];
  const loading = impactQuery.isPending;

  const totalRealized = summary?.total_realized_savings || 0;
  const totalEstimated = summary?.total_estimated_impact || 0;
  const completedCount = summary?.completed_actions_count || 0;
  const avgSavingsPerAction = completedCount > 0 ? Math.round(totalRealized / completedCount) : 0;

  // Chart data formatting
  const actionTypeChartData = Object.entries(summary?.savings_by_action_type || {}).map(([key, val]) => ({
    name: key.replace(/_/g, " "),
    savings: val,
  }));

  const siteChartData = Object.entries(summary?.savings_by_site || {}).map(([key, val]) => ({
    name: key,
    savings: val,
  }));

  return (
    <AppShell>
      <QueryError error={impactQuery.error} retry={impactQuery.refetch} />
      <QueryError error={sitesQuery.error} retry={sitesQuery.refetch} />
      {/* Header */}
      <section className="mb-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-black/10">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-2 bg-[#ff5a24] shadow-[0_0_0_1px_rgba(255,90,36,0.2)]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[#ff5a24]">
              Financial ROI &amp; Savings Ledger
            </span>
          </div>
          <h1
            className="text-4xl sm:text-5xl font-medium tracking-tight text-black mt-1"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            Avoided Cost &amp; Impact
          </h1>
          <p className="text-sm text-[#5a5a5a] mt-1.5 max-w-2xl">
            Traceable financial savings calculated from completed fleet interventions, avoided idle standby days, and resolved surcharge penalties.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-black/10 bg-white/70 px-3.5 py-2 shadow-sm text-xs font-mono">
          <DollarSign className="size-4 text-[#ff5a24]" />
          <span className="text-black font-semibold">Realized: {summary ? formatCurrency(totalRealized, { showDecimals: true }) : "—"}</span>
        </div>
      </section>

      {/* KPI Cards */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5 mb-10">
        <MetricCard
          title="Total Realized Savings"
          value={summary ? formatCurrency(totalRealized) : "—"}
          subtext="Verified from completed actions"
          trend="Realized ROI"
          trendPositive={true}
          sparklineColor="#16a34a"
          statusDotColor="bg-emerald-500"
        />
        <MetricCard
          title="Total Estimated Impact"
          value={summary ? formatCurrency(totalEstimated) : "—"}
          subtext="Potential savings from open recs"
          trend="Projected"
          trendPositive={true}
          sparklineColor="#ff5a24"
          statusDotColor="bg-[#ff5a24]"
        />
        <MetricCard
          title="Completed Operations"
          value={summary ? completedCount : "—"}
          subtext="Interventions executed & resolved"
          trend="Verified"
          trendPositive={true}
          sparklineColor="#2563eb"
          statusDotColor="bg-blue-500"
        />
        <MetricCard
          title="Avg Savings / Action"
          value={summary ? formatCurrency(avgSavingsPerAction) : "—"}
          subtext="Per operational resolution"
          trend="High Efficiency"
          trendPositive={true}
          sparklineColor="#8b5cf6"
          statusDotColor="bg-purple-500"
        />
      </section>

      {/* Site Filter Tabs */}
      <section className="mb-6 flex flex-wrap items-center gap-2 p-4 rounded-2xl border border-black/10 bg-white/60 backdrop-blur shadow-sm">
        <span className="text-xs font-semibold text-black uppercase tracking-wider flex items-center gap-1.5 mr-2">
          <Building2 className="size-3.5 text-[#ff5a24]" />
          Filter Site:
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
          All Jobsite Zones
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
      </section>

      {/* Recharts Breakdown Section */}
      <section className="mb-10 grid md:grid-cols-2 gap-8 items-stretch">
        {/* Savings by Action Type */}
        <GlassCard className="p-7">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Savings by Action Category
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">
                Financial impact breakdown across fleet intervention models
              </p>
            </div>
            <span className="text-xs font-mono text-[#ff5a24] bg-white px-2.5 py-1 rounded-full border border-black/10">
              INR
            </span>
          </div>

          <div className="h-64 w-full">
            {actionTypeChartData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-xs text-[#888]">
                Execute and complete actions in the Action Queue to populate realized category metrics.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={actionTypeChartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                  <XAxis dataKey="name" stroke="#888" fontSize={11} />
                  <YAxis stroke="#888" fontSize={11} />
                  <Tooltip
                    formatter={(val) => [formatCurrency(Number(val)), "Savings"]}
                    contentStyle={{
                      backgroundColor: "#111111",
                      borderRadius: "12px",
                      border: "1px solid rgba(255,255,255,0.2)",
                      color: "#ffffff",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="savings" fill="#ff5a24" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlassCard>

        {/* Savings by Jobsite */}
        <GlassCard className="p-7">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Savings by Jobsite Infrastructure
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">
                Distribution of cost avoidance across active project sites
              </p>
            </div>
            <span className="text-xs font-mono text-emerald-600 bg-white px-2.5 py-1 rounded-full border border-black/10">
              By Site
            </span>
          </div>

          <div className="h-64 w-full">
            {siteChartData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-xs text-[#888]">
                Execute and complete actions in the Action Queue to populate realized site metrics.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={siteChartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                  <XAxis dataKey="name" stroke="#888" fontSize={10} />
                  <YAxis stroke="#888" fontSize={11} />
                  <Tooltip
                    formatter={(val) => [formatCurrency(Number(val)), "Savings"]}
                    contentStyle={{
                      backgroundColor: "#111111",
                      borderRadius: "12px",
                      border: "1px solid rgba(255,255,255,0.2)",
                      color: "#ffffff",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="savings" fill="#111111" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlassCard>
      </section>

      {/* Realized Savings Audit Ledger */}
      <section className="mb-12">
        <GlassCard className="p-7">
          <div className="flex items-center justify-between pb-4 border-b border-black/10 mb-5">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Realized Savings Audit Ledger
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">
                Deterministic calculation basis for every rupee of claimed ROI
              </p>
            </div>
            <span className="text-xs font-mono text-[#7a7a7a]">
              {(summary?.recent_impact_records || []).length} Verified Records
            </span>
          </div>

          {loading ? (
            <TableSkeleton />
          ) : (summary?.recent_impact_records || []).length === 0 ? (
            <div className="py-12 text-center text-xs text-[#7a7a7a]">
              No realized savings records yet. Head over to the{" "}
              <Link href="/actions" className="text-[#ff5a24] font-semibold underline">
                Action Queue
              </Link>{" "}
              to complete operational interventions.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/10 text-[10px] uppercase font-bold text-[#666]">
                    <th className="pb-3">Action ID</th>
                    <th className="pb-3">Equipment</th>
                    <th className="pb-3">Impact Type</th>
                    <th className="pb-3 text-right">Realized Savings</th>
                    <th className="pb-3 pl-4">Deterministic Calculation Basis</th>
                    <th className="pb-3 text-right">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5">
                  {(summary?.recent_impact_records || []).map((rec) => (
                    <tr key={rec.id} className="hover:bg-black/[0.02] transition-colors">
                      <td className="py-3.5 font-mono text-[#666]">
                        #{rec.action_id || rec.id}
                      </td>
                      <td className="py-3.5 font-bold text-black">
                        <Link
                          href={`/assets/${rec.equipment_id}`}
                          className="hover:text-[#ff5a24] transition-colors flex items-center gap-1"
                        >
                          <span>{rec.equipment_id}</span>
                          <ArrowUpRight className="size-3 text-[#888]" />
                        </Link>
                      </td>
                      <td className="py-3.5">
                        <span className="px-2.5 py-0.5 rounded-full font-mono text-[10px] font-semibold bg-black/5 text-black border border-black/10">
                          {rec.impact_type}
                        </span>
                      </td>
                      <td className="py-3.5 text-right font-mono font-bold text-emerald-600 text-sm">
                        +{formatCurrency(rec.realized_amount, { showDecimals: true })}
                      </td>
                      <td className="py-3.5 pl-4 text-[#555] leading-snug max-w-md font-mono text-[11px]">
                        {rec.calculation_basis}
                      </td>
                      <td className="py-3.5 text-right text-[#777] font-mono text-[11px]">
                        {new Date(rec.calculated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
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
