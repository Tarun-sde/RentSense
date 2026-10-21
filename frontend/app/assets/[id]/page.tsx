"use client";

import React, { useState } from "react";
import dynamic from "next/dynamic";
import { useApiQuery } from "@/lib/useApiQuery";
import { QueryError } from "@/components/ui/QueryError";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  DollarSign,
  Fuel,
  Gauge,
  QrCode,
  ShieldAlert,
  Sparkles,
  CheckCircle2,
  ArrowRight,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { AppShell } from "@/components/layout/AppShell";
import { GlassCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
const TelemetryChart = dynamic(() => import("@/components/assets/TelemetryChart").then(m => m.TelemetryChart), { loading: () => <div className="h-80 animate-pulse rounded-xl bg-black/5" /> });
const MiniMap = dynamic(() => import("@/components/assets/MiniMap").then(m => m.MiniMap), { ssr: false, loading: () => <div className="h-64 animate-pulse rounded-xl bg-black/5" /> });
import { CardSkeleton } from "@/components/ui/SkeletonLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { CheckoutModal } from "@/components/handoff/CheckoutModal";
import { CheckinModal } from "@/components/handoff/CheckinModal";
import { triggerActionFromRecommendation } from "@/lib/api";
import { useTelemetryStream } from "@/lib/useTelemetryStream";
import { EquipmentDetail, Anomaly, Recommendation } from "@/types";
import { cn, formatCurrency } from "@/lib/utils";

export default function AssetDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const detailQuery = useApiQuery<EquipmentDetail>(`/equipment/${encodeURIComponent(id)}`, Boolean(id));
  const anomaliesQuery = useApiQuery<Anomaly[]>(`/equipment/${encodeURIComponent(id)}/anomalies`, Boolean(id));
  const recommendationsQuery = useApiQuery<Recommendation[]>(`/recommendations/equipment/${encodeURIComponent(id)}`, Boolean(id));
  const equipment = detailQuery.data;
  const anomalies = anomaliesQuery.data ?? [];
  const recommendations = recommendationsQuery.data ?? [];
  const loading = detailQuery.isPending;
  const [isTriggeringAction, setIsTriggeringAction] = useState(false);

  // Workflow Modal States
  const [checkoutModalOpen, setCheckoutModalOpen] = useState(false);
  const [checkinModalOpen, setCheckinModalOpen] = useState(false);

  const loadDetail = () => Promise.all([detailQuery.refetch(), anomaliesQuery.refetch(), recommendationsQuery.refetch()]);
  const { connectionState } = useTelemetryStream();

  if (loading) {
    return (
      <AppShell>
        <div className="space-y-8 animate-pulse">
          <div className="h-8 w-48 bg-black/10 rounded-lg" />
          <div className="grid lg:grid-cols-4 gap-6">
            {[...Array(4)].map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
          <div className="h-96 bg-black/10 rounded-2xl" />
        </div>
      </AppShell>
    );
  }

  if (!equipment) {
    return (
      <AppShell>
        <QueryError error={detailQuery.error} retry={loadDetail} />
        <EmptyState
          title="Equipment Asset Not Found"
          description={`No record found for asset identifier "${id}". Please check the fleet registry.`}
          actionText="Back to Fleet Assets"
          onAction={() => router.push("/assets")}
        />
      </AppShell>
    );
  }

  const metadata = equipment.metadata_json as { model?: string; serial?: string } | null;
  const model = metadata?.model || "Standard Heavy Spec";
  const serial = metadata?.serial || "SN-PENDING";
  const utilPct = Math.round(equipment.utilization_rate * 100);
  const engineHours = equipment.latest_telemetry?.engine_hours || 0;
  const idleHours = equipment.latest_telemetry?.idle_hours || 0;
  const fuelPct = equipment.latest_telemetry?.fuel_pct ?? 100;
  const activeHours = Math.max(0, Math.round((engineHours - idleHours) * 100) / 100);

  const hasActiveRental = Boolean(
    equipment.current_rental && !equipment.current_rental.checked_in_at
  );

  return (
    <AppShell connectionState={connectionState}>
      <QueryError error={detailQuery.error || anomaliesQuery.error || recommendationsQuery.error} retry={loadDetail} />
      {/* Breadcrumb & Navigation */}
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/assets"
          className="inline-flex items-center gap-2 text-xs font-semibold text-[#6a6a6a] hover:text-black transition-colors"
        >
          <ArrowLeft className="size-3.5" />
          <span>Back to Fleet Ledger</span>
        </Link>
        <span className="text-xs font-mono text-[#7a7a7a]">
          Node ID: <strong className="text-black">{equipment.id}</strong>
        </span>
      </div>

      {/* Main Asset Header */}
      <section className="mb-8 flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-black/10">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1
              className="text-4xl sm:text-5xl font-medium tracking-tight text-black"
              style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
            >
              {equipment.id}
            </h1>
            <StatusBadge status={equipment.status} size="lg" />
          </div>

          <p className="mt-2 text-base text-[#4c4c4c] flex flex-wrap items-center gap-2">
            <span className="font-semibold text-black">{equipment.type}</span>
            <span>•</span>
            <span>{model}</span>
            <span>•</span>
            <span>{equipment.dealer}</span>
            <span>•</span>
            <span className="font-mono text-xs text-[#7a7a7a]">Serial: {serial}</span>
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/scan"
            className="flex items-center gap-2 rounded-xl border border-black/15 bg-white/70 px-4 py-2.5 text-xs font-medium text-black shadow-sm hover:bg-white transition-all"
          >
            <QrCode className="size-4 text-[#ff5a24]" />
            <span>Scan Terminal</span>
          </Link>

          {hasActiveRental ? (
            <button
              onClick={() => setCheckinModalOpen(true)}
              className="flex items-center gap-2 rounded-xl bg-emerald-700 px-5 py-2.5 text-xs font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)] hover:bg-emerald-800 transition-all"
            >
              <ShieldCheck className="size-4" />
              <span>Check In Equipment</span>
            </button>
          ) : (
            <button
              onClick={() => setCheckoutModalOpen(true)}
              className="flex items-center gap-2 rounded-xl bg-[#111111] px-5 py-2.5 text-xs font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)] hover:bg-black transition-all"
            >
              <ArrowRight className="size-4 text-[#ff5a24]" />
              <span>Check Out (Dispatch)</span>
            </button>
          )}
        </div>
      </section>

      {/* 4 Metric KPI Cards */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <GlassCard className="p-6 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#6a6a6a]">Engine Runtime</span>
            <Gauge className="size-4 text-[#ff5a24]" />
          </div>
          <p
            className="text-3xl sm:text-4xl font-medium text-black mt-3 leading-none transition-all"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {engineHours.toFixed(2)}h
          </p>
          <span className="text-[11px] text-[#7a7a7a] mt-2">
            Active: <strong className="text-black">{activeHours.toFixed(2)}h</strong> • Idle: <strong className="text-black">{idleHours.toFixed(2)}h</strong>
          </span>
        </GlassCard>

        <GlassCard className="p-6 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#6a6a6a]">Utilization Rate</span>
            <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <p
            className="text-3xl sm:text-4xl font-medium text-black mt-3 leading-none transition-all"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {utilPct}%
          </p>
          <div className="w-full bg-black/10 h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-500", utilPct < 20 ? "bg-amber-500" : "bg-[#ff5a24]")}
              style={{ width: `${Math.min(100, Math.max(5, utilPct))}%` }}
            />
          </div>
        </GlassCard>

        <GlassCard className="p-6 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#6a6a6a]">Fuel Reservoir</span>
            <Fuel className="size-4 text-[#ff5a24]" />
          </div>
          <p
            className="text-3xl sm:text-4xl font-medium text-black mt-3 leading-none font-mono transition-all"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {fuelPct.toFixed(1)}%
          </p>
          <span className="text-[11px] text-[#7a7a7a] mt-2">
            Estimated ~{Math.round(fuelPct * 3.5)} Liters remaining
          </span>
        </GlassCard>

        <GlassCard className="p-6 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-[#6a6a6a]">Contract Day Rate</span>
            <DollarSign className="size-4 text-emerald-600" />
          </div>
          <p
            className="text-3xl sm:text-4xl font-medium text-black mt-3 leading-none font-mono"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {formatCurrency(equipment.daily_rate)}
          </p>
          <span className="text-[11px] text-[#7a7a7a] mt-2">
            Supplier: <strong className="text-black">{equipment.dealer}</strong>
          </span>
        </GlassCard>
      </section>

      {/* Center Layout: Telemetry Charts (2 cols) + Assignment & MiniMap (1 col) */}
      <section className="grid lg:grid-cols-3 gap-8 mb-8 items-stretch">
        <div className="lg:col-span-2">
          <TelemetryChart telemetry={equipment.recent_telemetry} />
        </div>
        <div className="space-y-6 flex flex-col justify-between">
          {/* Active Assignment Card */}
          <GlassCard className="p-6 flex-1 flex flex-col justify-between">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Current Deployment
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">Active site &amp; operator assignment</p>
            </div>

            <div className="my-4 space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-black/[0.03] border border-black/5">
                <span className="text-[10px] uppercase font-bold text-[#7a7a7a] block">Assigned Site</span>
                <span className="font-semibold text-black text-sm mt-0.5 block">
                  {equipment.site?.name || "Yard Staging Depot"}
                </span>
                <span className="text-[11px] text-[#666] block mt-0.5">
                  {equipment.site?.location || "Central Storage Logistics"}
                </span>
              </div>

              <div className="p-3 rounded-xl bg-black/[0.03] border border-black/5">
                <span className="text-[10px] uppercase font-bold text-[#7a7a7a] block">Certified Operator</span>
                <span className="font-semibold text-black text-sm mt-0.5 block">
                  {equipment.operator?.name || (
                    <span className="text-[#ff5a24]">Missing Assignment</span>
                  )}
                </span>
                <span className="text-[11px] text-[#666] block mt-0.5">
                  {equipment.operator?.contact || "No operator contact linked"}
                </span>
              </div>
            </div>

            <div className="text-[11px] text-[#7a7a7a] flex items-center justify-between border-t border-black/10 pt-3">
              <span>Checkout: {equipment.current_rental?.checked_out_at ? new Date(equipment.current_rental.checked_out_at).toLocaleDateString() : "N/A"}</span>
              <span>Due: {equipment.current_rental?.due_at ? new Date(equipment.current_rental.due_at).toLocaleDateString() : "N/A"}</span>
            </div>
          </GlassCard>

          {/* MiniMap with Live GPS Pinpoint */}
          <div className="h-60">
            <MiniMap
              site={equipment.site}
              latitude={equipment.latest_telemetry?.latitude}
              longitude={equipment.latest_telemetry?.longitude}
            />
          </div>
        </div>
      </section>

      {/* AI Operational Insight & Active Alerts */}
      <section className="grid md:grid-cols-2 gap-8 mb-8 items-stretch">
        {/* AI Insight & Recommendation Card */}
        <GlassCard variant="dark" className="p-7 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-[#ff5a24]" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-white">
                  Recommendation &amp; Action
                </h3>
              </div>
              <div className="flex items-center gap-2">
                {recommendations.length > 0 && recommendations[0].estimated_impact?.estimated_savings_usd ? (
                  <span className="text-xs font-mono text-emerald-400 bg-emerald-500/20 px-2.5 py-0.5 rounded-full border border-emerald-500/40 font-bold">
                    +${Math.round(recommendations[0].estimated_impact.estimated_savings_usd).toLocaleString()} Avoidable Loss
                  </span>
                ) : anomalies.length > 0 ? (
                  <span className="text-xs font-mono text-[#ff5a24] bg-white/10 px-2.5 py-0.5 rounded-full border border-white/20">
                    Anomaly Score: <strong>{anomalies[0].anomaly_score}</strong>/100
                  </span>
                ) : (
                  <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/30">
                    Healthy (Score: 0/100)
                  </span>
                )}
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {recommendations.length > 0 ? (
                recommendations.map((rec) => (
                  <div
                    key={rec.id}
                    className="rounded-xl border border-white/15 bg-white/10 p-4 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                          {rec.recommendation_type}
                        </span>
                        <span
                          className={cn(
                            "text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded border",
                            rec.priority === "CRITICAL"
                              ? "bg-red-500/20 text-red-300 border-red-500/40"
                              : "bg-[#ff5a24]/20 text-[#ff8a5c] border-[#ff5a24]/40"
                          )}
                        >
                          {rec.priority}
                        </span>
                      </div>
                      <span className="text-[10px] text-white/60 font-mono">
                        {Math.round(rec.confidence * 100)}% Confidence
                      </span>
                    </div>

                    <p className="text-xs text-white/90 leading-relaxed">
                      {rec.explanation}
                    </p>

                    {rec.estimated_impact?.calculation_basis && (
                      <div className="rounded-lg bg-black/40 p-2.5 text-[11px] font-mono text-emerald-300 border border-emerald-500/20">
                        {rec.estimated_impact.calculation_basis}
                      </div>
                    )}
                  </div>
                ))
              ) : anomalies.length > 0 ? (
                anomalies.map((anom, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-white space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm">{anom.anomaly_type.replace("_", " ")}</span>
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-black/40 border border-white/20">
                        {anom.severity}
                      </span>
                    </div>
                    <p className="text-xs text-white/90 leading-relaxed">{anom.explanation}</p>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
                  <p className="font-semibold text-white text-sm">
                    Operational Performance Optimal
                  </p>
                  <p className="text-xs text-white/80 mt-1 leading-relaxed">
                    Asset {equipment.id} is operating within nominal thresholds. No excessive idle, overdue contracts, or allocation anomalies detected.
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-white/10 flex items-center justify-between text-xs text-white/70">
            <span>Deterministic ROI Calibrated</span>
            {recommendations.length > 0 ? (
              <button
                disabled={isTriggeringAction}
                onClick={async () => {
                  try {
                    setIsTriggeringAction(true);
                    await triggerActionFromRecommendation(recommendations[0].id, {
                      action_type: recommendations[0].recommendation_type,
                      notes: `Executed from Asset Detail (${equipment.id}): ${recommendations[0].action}`,
                      actor: "Commander Marcus Vance",
                      payload: recommendations[0].estimated_impact || {},
                    });
                    router.push("/actions");
                  } catch (err: unknown) {
                    alert(`Error triggering action: ${err instanceof Error ? err.message : "Unknown error"}`);
                  } finally {
                    setIsTriggeringAction(false);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#ff5a24] px-4 py-2 text-xs font-semibold text-white hover:bg-[#ff6330] transition-colors disabled:opacity-50"
              >
                <Zap className="size-3.5" />
                <span>{isTriggeringAction ? "Queuing..." : `Execute ${recommendations[0].recommendation_type}`}</span>
              </button>
            ) : hasActiveRental ? (
              <button
                onClick={() => setCheckinModalOpen(true)}
                className="rounded-lg bg-[#ff5a24] px-4 py-2 text-xs font-semibold text-white hover:bg-[#ff6330] transition-colors"
              >
                Check In &amp; Return
              </button>
            ) : (
              <button
                onClick={() => setCheckoutModalOpen(true)}
                className="rounded-lg bg-[#ff5a24] px-4 py-2 text-xs font-semibold text-white hover:bg-[#ff6330] transition-colors"
              >
                Dispatch to Site
              </button>
            )}
          </div>
        </GlassCard>



        {/* Active Alerts for this asset */}
        <GlassCard variant="light" className="p-7 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="size-4 text-[#ff5a24]" />
                <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                  Asset Anomaly Logs
                </h3>
              </div>
              <span className="text-xs font-mono text-[#7a7a7a]">
                {equipment.active_alerts.length} Active
              </span>
            </div>

            <div className="mt-5 space-y-3">
              {equipment.active_alerts.length === 0 ? (
                <div className="py-8 text-center text-xs text-[#7a7a7a]">
                  <CheckCircle2 className="size-6 text-emerald-600 mx-auto mb-2" />
                  No open anomalies detected for {equipment.id}.
                </div>
              ) : (
                equipment.active_alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="p-4 rounded-xl border border-black/10 bg-white/70 shadow-xs space-y-1"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-black">{alert.alert_type}</span>
                      <span className="font-mono text-[10px] text-[#ff5a24] font-semibold uppercase">
                        {alert.severity}
                      </span>
                    </div>
                    <p className="text-xs text-[#555] leading-snug">{alert.message}</p>
                    <span className="text-[10px] text-[#888] font-mono block pt-1">
                      Reported: {new Date(alert.created_at).toLocaleString()}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-black/10 text-xs text-[#7a7a7a] flex items-center justify-between">
            <span>Automated Diagnostic Surveillance</span>
            <span className="text-emerald-700 font-semibold">Sensor Grid Synced</span>
          </div>
        </GlassCard>
      </section>

      {/* Rental History & Audit Timeline */}
      <section className="grid lg:grid-cols-2 gap-8 mb-12">
        {/* Rental Contracts History */}
        <GlassCard className="p-7">
          <div className="flex items-center justify-between pb-4 border-b border-black/10">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
              Rental Contract History
            </h3>
            <span className="text-xs font-mono text-[#7a7a7a]">
              {equipment.rental_history.length} Record(s)
            </span>
          </div>

          <div className="mt-4 space-y-3">
            {equipment.rental_history.map((rental) => (
              <div
                key={rental.id}
                className="p-3.5 rounded-xl border border-black/5 bg-white/50 text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between font-semibold text-black">
                  <span>Contract #{rental.id}</span>
                  <span className="font-mono">${rental.daily_rate}/day</span>
                </div>
                <div className="text-[#666] flex flex-wrap items-center gap-2 text-[11px]">
                  <span>Site: {rental.site?.name || "Yard"}</span>
                  <span>•</span>
                  <span>Operator: {rental.operator?.name || "Unassigned"}</span>
                </div>
                {rental.condition_notes && (
                  <p className="text-[11px] text-[#777] italic pt-1">
                    &quot;{rental.condition_notes}&quot;
                  </p>
                )}
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Audit Timeline */}
        <GlassCard className="p-7">
          <div className="flex items-center justify-between pb-4 border-b border-black/10">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
              Lifecycle Audit Events
            </h3>
            <span className="text-xs font-mono text-[#7a7a7a]">
              {equipment.audit_timeline.length} Event(s)
            </span>
          </div>

          <div className="mt-4 space-y-3">
            {equipment.audit_timeline.length === 0 ? (
              <p className="py-6 text-center text-xs text-[#7a7a7a]">
                No recorded audit events for this equipment yet.
              </p>
            ) : (
              equipment.audit_timeline.map((evt) => (
                <div
                  key={evt.id}
                  className="p-3 rounded-xl border border-black/5 bg-white/50 text-xs flex items-start justify-between gap-3"
                >
                  <div>
                    <span className="font-semibold text-black block">{evt.event_type}</span>
                    <span className="text-[11px] text-[#666] block">
                      Actor: {evt.actor || "Automated Process"}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-[#888] shrink-0">
                    {new Date(evt.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              ))
            )}
          </div>
        </GlassCard>
      </section>

      {/* Checkout Modal */}
      <CheckoutModal
        isOpen={checkoutModalOpen}
        onClose={() => setCheckoutModalOpen(false)}
        equipmentId={equipment.id}
        equipmentType={equipment.type}
        dailyRate={equipment.daily_rate}
        dealer={equipment.dealer}
        onSuccess={() => {
        }}
      />

      {/* Checkin Modal */}
      <CheckinModal
        isOpen={checkinModalOpen}
        onClose={() => setCheckinModalOpen(false)}
        equipmentId={equipment.id}
        equipmentType={equipment.type}
        currentSiteName={equipment.site?.name}
        currentOperatorName={equipment.operator?.name}
        currentStatus={equipment.status}
        onSuccess={() => {
        }}
      />
    </AppShell>
  );
}
