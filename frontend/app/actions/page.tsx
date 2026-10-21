"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Zap,
  CheckCircle2,
  Clock,
  ArrowUpRight,
  Filter,
  Plus,
  Check,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { GlassCard } from "@/components/ui/GlassCard";
import { MetricCard } from "@/components/ui/MetricCard";
import { TableSkeleton } from "@/components/ui/SkeletonLoader";
import {
  completeAction,
  cancelAction,
  createAction,
} from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { QueryError } from "@/components/ui/QueryError";
import { Action, Site, EquipmentListItem } from "@/types";
import { cn, getErrorMessage } from "@/lib/utils";

export default function ActionsPage() {
  const actionsQuery = useApiQuery<Action[]>("/actions");
  const sitesQuery = useApiQuery<Site[]>("/sites");
  const equipmentQuery = useApiQuery<EquipmentListItem[]>("/equipment");
  const actions = actionsQuery.data ?? [];
  const sites = sitesQuery.data ?? [];
  const equipmentList = equipmentQuery.data ?? [];
  const loading = actionsQuery.isPending;
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [selectedType, setSelectedType] = useState<string>("ALL");

  // Complete Action Modal State
  const [completingAction, setCompletingAction] = useState<Action | null>(null);
  const [completeNotes, setCompleteNotes] = useState("");
  const [targetSiteId, setTargetSiteId] = useState("SITE-003");
  const [extensionDays, setExtensionDays] = useState(7);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // New Action Modal State
  const [newActionModalOpen, setNewActionModalOpen] = useState(false);
  const [newEqId, setNewEqId] = useState("EQX1001");
  const [newType, setNewType] = useState("REASSIGN");
  const [newPriority, setNewPriority] = useState("HIGH");
  const [newNotes, setNewNotes] = useState("");

  const handleCompleteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!completingAction) return;

    try {
      setIsSubmitting(true);
      const payload: Record<string, unknown> = {};
      if (completingAction.action_type === "REASSIGN") {
        payload.target_site_id = targetSiteId;
      } else if (completingAction.action_type === "EXTEND") {
        payload.extension_days = extensionDays;
      }

      await completeAction(completingAction.id, {
        notes: completeNotes || `Executed ${completingAction.action_type} operation`,
        actor: "Commander Marcus Vance",
        payload,
      });

      setCompletingAction(null);
      setCompleteNotes("");
    } catch (err: unknown) {
      alert(`Error completing action: ${getErrorMessage(err, "Unknown error")}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelClick = async (actionId: number) => {
    if (!confirm("Are you sure you want to cancel this operational action?")) return;
    try {
      await cancelAction(actionId, {
        reason: "Operator dismissed from Action Queue",
        actor: "Commander Marcus Vance",
      });
    } catch (err: unknown) {
      alert(`Error cancelling action: ${getErrorMessage(err, "Unknown error")}`);
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsSubmitting(true);
      await createAction({
        equipment_id: newEqId,
        action_type: newType,
        priority: newPriority,
        notes: newNotes || `Manual ${newType} action initiated`,
        actor: "Commander Marcus Vance",
      });
      setNewActionModalOpen(false);
      setNewNotes("");
    } catch (err: unknown) {
      alert(`Error creating action: ${getErrorMessage(err, "Unknown error")}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredActions = actions.filter((a) => {
    const matchStatus = selectedStatus === "ALL" || a.status === selectedStatus;
    const matchType = selectedType === "ALL" || a.action_type === selectedType;
    return matchStatus && matchType;
  });

  const pendingCount = actions.filter((a) => a.status === "PENDING" || a.status === "IN_PROGRESS").length;
  const completedCount = actions.filter((a) => a.status === "COMPLETED").length;

  const getPriorityBadge = (priority: string) => {
    switch (priority.toUpperCase()) {
      case "CRITICAL":
        return "bg-red-500/20 text-red-700 border-red-300";
      case "HIGH":
        return "bg-[#ff5a24]/20 text-[#ff5a24] border-[#ff5a24]/30";
      case "MEDIUM":
        return "bg-amber-500/20 text-amber-800 border-amber-300";
      default:
        return "bg-slate-500/20 text-slate-700 border-slate-300";
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "COMPLETED":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      case "IN_PROGRESS":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "CANCELLED":
        return "bg-gray-100 text-gray-600 border-gray-300";
      default:
        return "bg-amber-100 text-amber-800 border-amber-300";
    }
  };

  return (
    <AppShell>
      <QueryError error={actionsQuery.error} retry={actionsQuery.refetch} />
      <QueryError error={sitesQuery.error} retry={sitesQuery.refetch} />
      <QueryError error={equipmentQuery.error} retry={equipmentQuery.refetch} />
      {/* Header */}
      <section className="mb-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-black/10">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-2 bg-[#ff5a24] shadow-[0_0_0_1px_rgba(255,90,36,0.2)]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[#ff5a24]">
              Operational Intelligence Loop
            </span>
          </div>
          <h1
            className="text-4xl sm:text-5xl font-medium tracking-tight text-black mt-1"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            Action Queue
          </h1>
          <p className="text-sm text-[#5a5a5a] mt-1.5 max-w-2xl">
            Triage, execute, and verify deterministic fleet interventions. Completing actions transitions rental state, resolves alerts, and computes verified financial impact.
          </p>
        </div>

        <button
          onClick={() => setNewActionModalOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-[#111111] px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-[#222222] transition-all"
        >
          <Plus className="size-4" />
          <span>New Action</span>
        </button>
      </section>

      {/* KPI Cards */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-5 mb-10">
        <MetricCard
          title="Active Actions"
          value={actionsQuery.data ? pendingCount : "—"}
          subtext="Requiring operator execution"
          trend="Actionable"
          trendPositive={true}
          sparklineColor="#ff5a24"
          statusDotColor="bg-[#ff5a24]"
        />
        <MetricCard
          title="Completed Interventions"
          value={actionsQuery.data ? completedCount : "—"}
          subtext="Fully verified & state updated"
          trend="Saved Impact"
          trendPositive={true}
          sparklineColor="#16a34a"
          statusDotColor="bg-emerald-500"
        />
        <MetricCard
          title="Total Action Ledger"
          value={actionsQuery.data ? actions.length : "—"}
          subtext="Audited operations"
          trend="Surveillance"
          trendPositive={true}
          sparklineColor="#2563eb"
          statusDotColor="bg-blue-500"
        />
        <MetricCard
          title="Execution Model"
          value="Deterministic"
          subtext="Traceable state transitions"
          trend="Audit Verified"
          trendPositive={true}
          sparklineColor="#8b5cf6"
          statusDotColor="bg-purple-500"
        />
      </section>

      {/* Filter Tabs */}
      <section className="mb-6 flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-black/10 bg-white/60 backdrop-blur shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-black uppercase tracking-wider flex items-center gap-1.5 mr-2">
            <Filter className="size-3.5 text-[#ff5a24]" />
            Status:
          </span>
          {["ALL", "PENDING", "COMPLETED", "CANCELLED"].map((s) => (
            <button
              key={s}
              onClick={() => setSelectedStatus(s)}
              className={cn(
                "px-3 py-1.5 rounded-xl text-xs font-medium transition-all",
                selectedStatus === s
                  ? "bg-[#111111] text-white shadow-sm"
                  : "bg-white/70 text-[#555] border border-black/10 hover:text-black"
              )}
            >
              {s === "ALL" ? "All Statuses" : s}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-black uppercase tracking-wider mr-2">
            Type:
          </span>
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="rounded-xl border border-black/10 bg-white px-3 py-1.5 text-xs font-medium text-black focus:outline-none focus:ring-1 focus:ring-[#ff5a24]"
          >
            <option value="ALL">All Action Types</option>
            <option value="RETURN">Return Asset</option>
            <option value="REASSIGN">Reassign Equipment</option>
            <option value="EXTEND">Extend Rental</option>
            <option value="INVESTIGATE">Investigate</option>
          </select>
        </div>
      </section>

      {/* Actions Ledger / Card List */}
      <section className="mb-12">
        <GlassCard className="p-7">
          <div className="flex items-center justify-between pb-4 border-b border-black/10 mb-5">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
                Operational Queue
              </h3>
              <p className="text-xs text-[#7a7a7a] mt-0.5">
                Execute pending actions to complete rental transitions and auto-resolve anomalies
              </p>
            </div>
            <span className="text-xs font-mono text-[#7a7a7a]">
              {filteredActions.length} Operations
            </span>
          </div>

          {loading ? (
            <TableSkeleton />
          ) : filteredActions.length === 0 ? (
            <div className="py-12 text-center text-xs text-[#7a7a7a]">
              No operational actions matching the selected filter criteria.
            </div>
          ) : (
            <div className="space-y-4">
              {filteredActions.map((action) => (
                <div
                  key={action.id}
                  className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm hover:shadow-md transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-2 max-w-2xl">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/assets/${action.equipment_id}`}
                        className="font-bold text-sm text-black hover:text-[#ff5a24] transition-colors flex items-center gap-1"
                      >
                        <span>{action.equipment_id}</span>
                        <ArrowUpRight className="size-3.5 text-[#888]" />
                      </Link>

                      <span
                        className={cn(
                          "text-[10px] px-2.5 py-0.5 rounded-full font-mono uppercase font-bold border",
                          getPriorityBadge(action.priority)
                        )}
                      >
                        {action.priority}
                      </span>

                      <span
                        className={cn(
                          "text-[10px] px-2.5 py-0.5 rounded-full font-mono uppercase font-semibold border",
                          getStatusBadge(action.status)
                        )}
                      >
                        {action.status}
                      </span>

                      <span className="text-[10px] text-[#777] font-mono">
                        Type: <strong>{action.action_type}</strong>
                      </span>

                      <span className="text-[10px] text-[#888] flex items-center gap-1 font-mono">
                        <Clock className="size-3" />
                        {new Date(action.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>

                    <p className="text-xs text-[#444] leading-relaxed">
                      {action.notes || `Perform ${action.action_type} operation on ${action.equipment_id}`}
                    </p>

                    {action.completed_at && (
                      <p className="text-[11px] text-emerald-700 font-medium flex items-center gap-1">
                        <CheckCircle2 className="size-3.5" />
                        Completed at {new Date(action.completed_at).toLocaleString()} by {action.actor}
                      </p>
                    )}
                  </div>

                  {/* Actions Buttons */}
                  <div className="flex items-center gap-2 shrink-0">
                    {action.status === "PENDING" || action.status === "IN_PROGRESS" ? (
                      <>
                        <button
                          onClick={() => setCompletingAction(action)}
                          className="inline-flex items-center gap-1.5 rounded-xl bg-[#ff5a24] px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#ff6330] transition-colors"
                        >
                          <Check className="size-3.5" />
                          <span>Complete Action</span>
                        </button>
                        <button
                          onClick={() => handleCancelClick(action.id)}
                          className="rounded-xl border border-black/15 bg-white px-3 py-2 text-xs font-medium text-[#666] hover:text-black hover:bg-black/5 transition-colors"
                        >
                          Cancel
                        </button>
                      </>
                    ) : action.status === "COMPLETED" ? (
                      <span className="text-xs font-mono text-emerald-600 bg-emerald-50 px-3 py-1.5 rounded-xl border border-emerald-200 flex items-center gap-1.5 font-semibold">
                        <CheckCircle2 className="size-4" />
                        Impact Realized
                      </span>
                    ) : (
                      <span className="text-xs font-mono text-gray-500 bg-gray-50 px-3 py-1.5 rounded-xl border border-gray-200">
                        Cancelled
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </section>

      {/* Complete Action Modal */}
      {completingAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-black/10 bg-[#fbf9f4] p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-black/10 pb-3">
              <div>
                <h3 className="text-base font-bold text-black flex items-center gap-2">
                  <Zap className="size-4 text-[#ff5a24]" />
                  Complete {completingAction.action_type} Action
                </h3>
                <p className="text-xs text-[#777]">
                  Asset: {completingAction.equipment_id} • Priority: {completingAction.priority}
                </p>
              </div>
              <button
                onClick={() => setCompletingAction(null)}
                className="text-[#888] hover:text-black"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCompleteSubmit} className="space-y-4 text-xs">
              {completingAction.action_type === "REASSIGN" && (
                <div>
                  <label className="block font-semibold text-black mb-1">
                    Destination Jobsite:
                  </label>
                  <select
                    value={targetSiteId}
                    onChange={(e) => setTargetSiteId(e.target.value)}
                    className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs font-medium text-black focus:ring-1 focus:ring-[#ff5a24]"
                  >
                    {sites.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.location})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {completingAction.action_type === "EXTEND" && (
                <div>
                  <label className="block font-semibold text-black mb-1">
                    Extend Contract Duration (Days):
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={90}
                    value={extensionDays}
                    onChange={(e) => setExtensionDays(Number(e.target.value))}
                    className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs font-medium text-black focus:ring-1 focus:ring-[#ff5a24]"
                  />
                </div>
              )}

              <div>
                <label className="block font-semibold text-black mb-1">
                  Resolution Notes &amp; Verification Details:
                </label>
                <textarea
                  rows={3}
                  value={completeNotes}
                  onChange={(e) => setCompleteNotes(e.target.value)}
                  placeholder={`Describe findings or handoff state for ${completingAction.equipment_id}...`}
                  className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs text-black focus:ring-1 focus:ring-[#ff5a24]"
                />
              </div>

              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-[11px] text-amber-900 leading-relaxed">
                Completing this action will transition rental status, auto-resolve matching alerts, and write a realized financial savings record.
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-black/10">
                <button
                  type="button"
                  onClick={() => setCompletingAction(null)}
                  className="px-4 py-2 rounded-xl border border-black/15 bg-white font-medium text-[#555] hover:text-black"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-xl bg-[#ff5a24] font-semibold text-white hover:bg-[#ff6330] disabled:opacity-50"
                >
                  {isSubmitting ? "Executing..." : "Confirm & Complete"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Action Modal */}
      {newActionModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-black/10 bg-[#fbf9f4] p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-black/10 pb-3">
              <h3 className="text-base font-bold text-black flex items-center gap-2">
                <Plus className="size-4 text-[#ff5a24]" />
                Initiate Fleet Action
              </h3>
              <button
                onClick={() => setNewActionModalOpen(false)}
                className="text-[#888] hover:text-black"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-black mb-1">Target Equipment:</label>
                <select
                  value={newEqId}
                  onChange={(e) => setNewEqId(e.target.value)}
                  className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs font-medium text-black focus:ring-1 focus:ring-[#ff5a24]"
                >
                  {equipmentList.map((eq) => (
                    <option key={eq.id} value={eq.id}>
                      {eq.id} - {eq.type} ({eq.status})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-black mb-1">Action Type:</label>
                  <select
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                    className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs font-medium text-black focus:ring-1 focus:ring-[#ff5a24]"
                  >
                    <option value="REASSIGN">Reassign Asset</option>
                    <option value="RETURN">Return / Off-Rent</option>
                    <option value="EXTEND">Extend Rental</option>
                    <option value="INVESTIGATE">Investigate</option>
                  </select>
                </div>
                <div>
                  <label className="block font-semibold text-black mb-1">Priority:</label>
                  <select
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value)}
                    className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs font-medium text-black focus:ring-1 focus:ring-[#ff5a24]"
                  >
                    <option value="CRITICAL">Critical</option>
                    <option value="HIGH">High</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="LOW">Low</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block font-semibold text-black mb-1">Action Notes:</label>
                <textarea
                  rows={3}
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  placeholder="Specify instructions or rationale for this fleet operation..."
                  className="w-full rounded-xl border border-black/10 bg-white p-2.5 text-xs text-black focus:ring-1 focus:ring-[#ff5a24]"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-black/10">
                <button
                  type="button"
                  onClick={() => setNewActionModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-black/15 bg-white font-medium text-[#555] hover:text-black"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-xl bg-[#111111] font-semibold text-white hover:bg-[#222222] disabled:opacity-50"
                >
                  {isSubmitting ? "Creating..." : "Queue Action"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
}
