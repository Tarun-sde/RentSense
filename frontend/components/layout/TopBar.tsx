"use client";

import React from "react";
import { Menu, Search, Bell } from "lucide-react";
import { ConnectionState } from "@/lib/useTelemetryStream";
import { cn } from "@/lib/utils";

interface TopBarProps {
  onMenuToggle?: () => void;
  openAlertsCount?: number;
  connectionState?: ConnectionState;
}

export function TopBar({
  onMenuToggle,
  openAlertsCount = 0,
  connectionState = "OFFLINE",
}: TopBarProps) {
  const getConnectionBadge = () => {
    switch (connectionState) {
      case "LIVE":
        return {
          dot: "bg-emerald-500 animate-pulse",
          text: "CONTROL TOWER LIVE",
          sub: "SSE Stream Active",
          border: "border-emerald-500/20 bg-emerald-50/60 text-emerald-800",
        };
      case "STALE":
        return {
          dot: "bg-amber-500", text: "TELEMETRY STALE", sub: "Awaiting fresh sensor data",
          border: "border-amber-500/20 bg-amber-50/60 text-amber-800",
        };
      case "POLLING":
        return {
          dot: "bg-blue-500 animate-pulse",
          text: "STREAM POLLING",
          sub: "Fallback 30s Cycle",
          border: "border-blue-500/20 bg-blue-50/60 text-blue-800",
        };
      case "RECONNECTING":
        return {
          dot: "bg-amber-500 animate-pulse",
          text: "RECONNECTING",
          sub: "Syncing Stream",
          border: "border-amber-500/20 bg-amber-50/60 text-amber-800",
        };
      default:
        return {
          dot: "bg-red-500",
          text: "OFFLINE",
          sub: "Stream Paused",
          border: "border-red-500/20 bg-red-50/60 text-red-800",
        };
    }
  };

  const badge = getConnectionBadge();

  return (
    <header className="sticky top-0 z-30 flex h-20 w-full items-center justify-between px-6 sm:px-10 lg:px-12 bg-white/40 border-b border-black/10 backdrop-blur-xl transition-all">
      {/* Left: Mobile Menu & Live Badge */}
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuToggle}
          className="grid size-10 place-items-center rounded-xl border border-black/15 bg-white/70 text-black shadow-sm lg:hidden hover:bg-white transition-colors"
          aria-label="Open navigation menu"
        >
          <Menu className="size-5" />
        </button>

        {/* Live Stream Indicator Badge */}
        <div
          className={cn(
            "flex items-center gap-2.5 rounded-full border px-3.5 py-1.5 shadow-sm transition-all",
            badge.border
          )}
        >
          <span className={cn("size-2 rounded-full", badge.dot)} />
          <span className="text-xs font-semibold uppercase tracking-wider">
            {badge.text}
          </span>
          <span className="hidden sm:inline text-[10px] opacity-75 font-mono border-l border-current/20 pl-2">
            {badge.sub}
          </span>
        </div>
      </div>

      {/* Center: Search Bar */}
      <div className="flex-1 max-w-md mx-4 hidden md:block">
        <div className="relative flex items-center">
          <Search className="absolute left-3.5 size-4 text-[#7a7a7a]" />
          <input
            type="text"
            placeholder="Search equipment ID, serial, model, dealer, site..."
            className="w-full rounded-xl border border-black/10 bg-white/60 pl-10 pr-4 py-2 text-xs font-normal text-black placeholder:text-[#8a8a8a] focus:bg-white focus:outline-none focus:ring-1 focus:ring-[#ff5a24] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-all"
          />
        </div>
      </div>

      {/* Right: Notification & Profile */}
      <div className="flex items-center gap-3.5">
        {/* Notifications button */}
        <button
          className="relative grid size-10 place-items-center rounded-xl border border-black/10 bg-white/60 text-black hover:bg-white transition-colors shadow-sm"
          aria-label="Alerts and notifications"
        >
          <Bell className="size-4.5" />
          {openAlertsCount > 0 && (
            <span className="absolute -top-1 -right-1 flex size-5 items-center justify-center rounded-full bg-[#ff5a24] text-[10px] font-bold text-white shadow-sm animate-pulse">
              {openAlertsCount}
            </span>
          )}
        </button>

        {/* User Profile Chip */}
        <div className="flex items-center gap-3 rounded-xl border border-black/10 bg-white/60 px-3 py-1.5 shadow-sm">
          <div className="size-7 rounded-lg bg-[#111111] grid place-items-center text-white text-xs font-semibold">
            OP
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-semibold text-black leading-tight">Fleet Operator</p>
            <p className="text-[10px] text-[#7a7a7a] leading-none">Operations Console</p>
          </div>
        </div>
      </div>
    </header>
  );
}
