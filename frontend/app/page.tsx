"use client";

import React from "react";
import dynamic from "next/dynamic";
import { useApiQuery } from "@/lib/useApiQuery";
import { QueryError } from "@/components/ui/QueryError";
import { AppShell } from "@/components/layout/AppShell";
import { HeroOverview } from "@/components/dashboard/HeroOverview";
import { MetricCard } from "@/components/ui/MetricCard";
const FleetStatusDonut = dynamic(() => import("@/components/dashboard/FleetStatusDonut").then(m => m.FleetStatusDonut), { loading: () => <CardSkeleton /> });
const FleetMapCard = dynamic(() => import("@/components/dashboard/FleetMapCard").then(m => m.FleetMapCard), { ssr: false, loading: () => <div className="h-96 animate-pulse rounded-2xl bg-black/5" /> });
import { AlertsPanel } from "@/components/dashboard/AlertsPanel";
import { RecommendationsPanel } from "@/components/dashboard/RecommendationsPanel";
import { ActivityTimeline } from "@/components/dashboard/ActivityTimeline";
import { EquipmentTable } from "@/components/dashboard/EquipmentTable";
import { CardSkeleton, TableSkeleton } from "@/components/ui/SkeletonLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useTelemetryStream } from "@/lib/useTelemetryStream";
import { DashboardKPIs, EquipmentListItem, Alert, Recommendation } from "@/types";

export default function DashboardPage() {
  const kpiQuery = useApiQuery<DashboardKPIs>("/dashboard");
  const equipmentQuery = useApiQuery<EquipmentListItem[]>("/equipment");
  const alertsQuery = useApiQuery<Alert[]>("/alerts?status=OPEN");
  const recommendationsQuery = useApiQuery<Recommendation[]>("/recommendations?status=PENDING");
  const kpis = kpiQuery.data;
  const equipmentList = equipmentQuery.data ?? [];
  const alerts = alertsQuery.data ?? [];
  const recommendations = recommendationsQuery.data ?? [];
  const { connectionState } = useTelemetryStream();
  const loadInitialData = () => Promise.all([kpiQuery.refetch(), equipmentQuery.refetch(), alertsQuery.refetch(), recommendationsQuery.refetch()]);

  return (
    <AppShell
      openAlertsCount={kpis?.open_alerts ?? 0}
      connectionState={connectionState}
    >
      <QueryError error={kpiQuery.error} retry={kpiQuery.refetch} />
      {/* Hero Overview */}
      <HeroOverview
        fleetUtilizationPct={kpis?.fleet_utilization_pct}
        totalAssets={kpis?.total_equipment}
        activeAssets={kpis?.active}
      />

      {/* KPI Cards Grid */}
      <section className="mb-10">
        {kpiQuery.isPending ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5 sm:gap-5">
            {[...Array(5)].map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5 sm:gap-5">
            <MetricCard
              title="Active Fleet"
              value={kpis?.active ?? "—"}
              subtext="Under active rental contract"
              trend="In Production"
              trendPositive={true}
              sparklineColor="#16a34a"
              statusDotColor="bg-emerald-500"
            />
            <MetricCard
              title="Idle Units"
              value={kpis?.idle ?? "—"}
              subtext="High idle hours (>8h)"
              trend="Requires Action"
              trendPositive={false}
              sparklineColor="#eab308"
              statusDotColor="bg-amber-500"
            />
            <MetricCard
              title="Due Soon"
              value={kpis?.due_soon ?? "—"}
              subtext="Expiring within 48 hours"
              trend="Expiring"
              trendPositive={false}
              sparklineColor="#ff5a24"
              statusDotColor="bg-[#ff5a24]"
            />
            <MetricCard
              title="Overdue"
              value={kpis?.overdue ?? "—"}
              subtext="Surcharge accumulating"
              trend="Critical Surcharge"
              trendPositive={false}
              sparklineColor="#dc2626"
              statusDotColor="bg-red-600"
            />
            <MetricCard
              title="Unassigned"
              value={kpis?.unassigned ?? "—"}
              subtext="Missing operator or yard"
              trend="Off-Rent"
              trendPositive={true}
              sparklineColor="#64748b"
              statusDotColor="bg-slate-400"
            />
          </div>
        )}
      </section>

      {/* Center Section: Donut + Tactical Map */}
      <section className="mb-10 grid lg:grid-cols-3 gap-8 items-stretch">
        <div className="lg:col-span-1">
          {kpis ? <FleetStatusDonut
            statusCounts={kpis?.status_counts ?? {}}
            totalEquipment={kpis.total_equipment}
          /> : <CardSkeleton />}
        </div>
        <div className="lg:col-span-2">
          <FleetMapCard equipmentList={equipmentList} />
        </div>
      </section>

      {/* Triad Intelligence Section: Alerts + Recommendations + Timeline */}
      <section className="mb-10 grid md:grid-cols-2 lg:grid-cols-3 gap-8 items-stretch">
        <div>
          <QueryError error={alertsQuery.error} retry={alertsQuery.refetch} />
          <AlertsPanel alerts={alerts} />
        </div>
        <div>
          <QueryError error={recommendationsQuery.error} retry={recommendationsQuery.refetch} />
          <RecommendationsPanel
            recommendations={recommendations}

          />
        </div>
        <div>
          <ActivityTimeline />
        </div>
      </section>

      {/* Fleet Ledger Table */}
      <QueryError error={equipmentQuery.error} retry={equipmentQuery.refetch} />
      <section className="mb-12">
        {equipmentQuery.isPending ? (
          <TableSkeleton />
        ) : equipmentQuery.error && !equipmentQuery.data ? (
          <EmptyState
            title="Unable to Load Equipment Ledger"
            description="Fleet data is temporarily unavailable. Please retry."
            actionText="Retry Connection"
            onAction={loadInitialData}
          />
        ) : (
          <EquipmentTable equipmentList={equipmentList} />
        )}
      </section>
    </AppShell>
  );
}
