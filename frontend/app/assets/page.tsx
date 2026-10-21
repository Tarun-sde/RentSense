"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { GlassCard } from "@/components/ui/GlassCard";
import { AssetCard } from "@/components/assets/AssetCard";
import { AddEquipmentModal } from "@/components/assets/AddEquipmentModal";
import { EquipmentTable } from "@/components/dashboard/EquipmentTable";
import { CardSkeleton, TableSkeleton } from "@/components/ui/SkeletonLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { useApiQuery } from "@/lib/useApiQuery";
import { QueryError } from "@/components/ui/QueryError";
import { EquipmentListItem } from "@/types";
import { LayoutGrid, List, Search, Plus } from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";

export default function AssetsPage() {
  const equipmentQuery = useApiQuery<EquipmentListItem[]>("/equipment");
  const equipmentList = equipmentQuery.data ?? [];
  const loading = equipmentQuery.isPending;
  const error = equipmentQuery.error;
  const loadEquipment = () => equipmentQuery.refetch();
  const [showAddModal, setShowAddModal] = useState(false);

  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusTab, setStatusTab] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");

  // Compute summary stats
  const totalDailyRate = equipmentList.reduce((acc, eq) => acc + eq.daily_rate, 0);
  const activeCount = equipmentList.filter((eq) => eq.status === "ACTIVE").length;
  const idleCount = equipmentList.filter((eq) => eq.status === "IDLE").length;

  // Filtered items
  const filteredEquipment = equipmentList.filter((eq) => {
    const matchesSearch =
      eq.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      eq.type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      eq.dealer.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (eq.site?.name && eq.site.name.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesStatus =
      statusTab === "ALL" || eq.status.toUpperCase() === statusTab.toUpperCase();

    const matchesType =
      typeFilter === "ALL" || eq.type.toLowerCase() === typeFilter.toLowerCase();

    return matchesSearch && matchesStatus && matchesType;
  });

  const availableTypes = Array.from(new Set(equipmentList.map((eq) => eq.type)));

  return (
    <AppShell>
      <QueryError error={error} retry={loadEquipment} />
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#6a6a6a] mb-1.5">
            <span className="size-2 bg-[#ff5a24]" />
            <span>INVENTORY CATALOG</span>
          </div>
          <h1
            className="text-3xl sm:text-4xl lg:text-5xl font-medium tracking-tight text-black"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            Fleet Asset Registry
          </h1>
          <p className="mt-1.5 text-sm text-[#6a6a6a] max-w-xl">
            Real-time surveillance ledger for heavy machinery across all active construction sites
          </p>
        </div>

        {/* Right side: Add Equipment + View Mode Toggle */}
        <div className="flex items-center gap-3 self-start md:self-auto">
          <button
            id="add-equipment-button"
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#ff5a24] text-white text-xs font-semibold hover:bg-[#e04d1a] transition-all shadow-sm"
          >
            <Plus className="size-3.5" />
            <span>Add Equipment</span>
          </button>

          <div className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-white/70 p-1 shadow-sm">
          <button
            onClick={() => setViewMode("grid")}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
              viewMode === "grid"
                ? "bg-[#111111] text-white shadow-sm"
                : "text-[#666] hover:text-black"
            )}
          >
            <LayoutGrid className="size-3.5" />
            <span>Grid Cards</span>
          </button>
          <button
            onClick={() => setViewMode("table")}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
              viewMode === "table"
                ? "bg-[#111111] text-white shadow-sm"
                : "text-[#666] hover:text-black"
            )}
          >
            <List className="size-3.5" />
            <span>Table Ledger</span>
          </button>
          </div>
        </div>
      </div>

      {/* Top Metric Summary Cards */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <GlassCard className="p-5 flex flex-col justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#7a7a7a]">Total Assets</span>
          <p
            className="text-3xl font-medium text-black mt-2 leading-none"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {equipmentQuery.data ? equipmentList.length : "—"}
          </p>
          <span className="text-[11px] text-[#888] mt-2">Total registered fleet</span>
        </GlassCard>

        <GlassCard className="p-5 flex flex-col justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#7a7a7a]">Daily Rental Spend</span>
          <p
            className="text-3xl font-medium text-black mt-2 leading-none font-mono"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {equipmentQuery.data ? formatCurrency(totalDailyRate) : "—"}
          </p>
          <span className="text-[11px] text-[#888] mt-2">Active fleet day-rate</span>
        </GlassCard>

        <GlassCard className="p-5 flex flex-col justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#7a7a7a]">Production Active</span>
          <p
            className="text-3xl font-medium text-emerald-700 mt-2 leading-none"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {equipmentQuery.data ? activeCount : "—"} Units
          </p>
          <span className="text-[11px] text-emerald-600 mt-2">Optimal runtime efficiency</span>
        </GlassCard>

        <GlassCard className="p-5 flex flex-col justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-[#7a7a7a]">Under-Utilized</span>
          <p
            className="text-3xl font-medium text-amber-600 mt-2 leading-none"
            style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
          >
            {equipmentQuery.data ? idleCount : "—"} Units
          </p>
          <span className="text-[11px] text-amber-600 mt-2">&gt;8h idle accumulation</span>
        </GlassCard>
      </section>

      {/* Filter Tabs & Search Bar */}
      <section className="mb-8 space-y-4">
        {/* Status Filter Tabs */}
        <div className="flex flex-wrap items-center gap-2 border-b border-black/10 pb-3">
          {["ALL", "ACTIVE", "IDLE", "DUE_SOON", "OVERDUE", "UNASSIGNED"].map((tab) => (
            <button
              key={tab}
              onClick={() => setStatusTab(tab)}
              className={cn(
                "px-3.5 py-1.5 rounded-full text-xs font-medium transition-all capitalize",
                statusTab === tab
                  ? "bg-[#111111] text-white shadow-sm"
                  : "bg-white/60 text-[#555] hover:bg-white hover:text-black border border-black/10"
              )}
            >
              {tab === "ALL" ? "All Assets" : tab.replace("_", " ").toLowerCase()}
            </button>
          ))}
        </div>

        {/* Search & Sub-Filter Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="relative w-full sm:max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[#7a7a7a]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by ID, model, dealer, or site..."
              className="w-full rounded-xl border border-black/10 bg-white/70 pl-10 pr-4 py-2 text-xs text-black placeholder:text-[#8a8a8a] focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#ff5a24]"
            />
          </div>

          <div className="flex items-center gap-3 self-end sm:self-auto">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-xl border border-black/10 bg-white/70 px-3 py-2 text-xs text-black focus:outline-none focus:ring-1 focus:ring-[#ff5a24]"
            >
              <option value="ALL">All Equipment Types</option>
              {availableTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* Main Content Area */}
      <section className="mb-12">
        {loading ? (
          viewMode === "grid" ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...Array(6)].map((_, i) => (
                <CardSkeleton key={i} />
              ))}
            </div>
          ) : (
            <TableSkeleton />
          )
        ) : error && !equipmentQuery.data ? (
          <EmptyState
            title="Failed to Load Fleet Registry"
            description={error.message}
            actionText="Retry"
            onAction={loadEquipment}
          />
        ) : filteredEquipment.length === 0 ? (
          <EmptyState
            title="No Matching Equipment"
            description="No assets match the selected status filter and search query."
            actionText="Reset Filters"
            onAction={() => {
              setSearchQuery("");
              setStatusTab("ALL");
              setTypeFilter("ALL");
            }}
          />
        ) : viewMode === "grid" ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredEquipment.map((eq) => (
              <AssetCard key={eq.id} equipment={eq} />
            ))}
          </div>
        ) : (
          <EquipmentTable equipmentList={filteredEquipment} />
        )}
      </section>

      {/* Add Equipment Modal */}
      <AddEquipmentModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSuccess={() => setShowAddModal(false)}
      />
    </AppShell>
  );
}
