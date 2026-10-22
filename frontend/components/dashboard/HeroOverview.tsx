"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, QrCode } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { greetingForHour, millisecondsUntilNextGreeting } from "@/lib/greeting";

interface HeroOverviewProps {
  fleetUtilizationPct?: number;
  totalAssets?: number;
  activeAssets?: number;
}

export function HeroOverview({
  fleetUtilizationPct,
  totalAssets,
  activeAssets,
}: HeroOverviewProps) {
  const [greeting, setGreeting] = useState("Welcome");

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const update = () => {
      if (timer) clearTimeout(timer);
      const now = new Date();
      setGreeting(greetingForHour(now.getHours()));
      timer = setTimeout(update, millisecondsUntilNextGreeting(now));
    };
    const handleVisibility = () => {
      if (!document.hidden) update();
    };
    update();
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", update);
    return () => {
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", update);
    };
  }, []);

  return (
    <section className="relative w-full mb-10">
      <div className="grid lg:grid-cols-[1.1fr_0.9fr] gap-8 items-stretch">
        {/* Left: Operational Hero Callout */}
        <div className="flex flex-col justify-between py-2">
          <div>
            <div className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-wider text-[#222222] mb-4">
              <span className="size-2.5 bg-[#ff5a24] shadow-[0_0_0_1px_rgba(255,90,36,0.2)]" />
              <span>AUTONOMOUS FLEET CONTROL TOWER</span>
            </div>

            <h1
              className="text-4xl sm:text-5xl lg:text-6xl font-medium leading-[1.02] tracking-tight text-black"
              style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
            >
              {greeting},{" "}
              <span className="italic text-[#ff5a24] block sm:inline">
                Operator.
              </span>
            </h1>

            <p className="mt-4 text-base sm:text-lg font-normal text-[#4c4c4c] max-w-xl leading-relaxed">
              Fleet telemetry and rental status with{" "}
              <span className="font-semibold text-black">{totalAssets ?? "—"} heavy assets</span> under surveillance.
            </p>
          </div>

          {/* Action Row */}
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link
              href="/assets"
              className="inline-flex items-center justify-center gap-3 h-13 px-6 rounded-xl bg-[#111111] text-white font-medium text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.15),0_12px_28px_rgba(0,0,0,0.12)] hover:bg-black transition-all"
            >
              <span>Explore Fleet Grid</span>
              <ArrowRight className="size-4 text-[#ff5a24]" />
            </Link>

            <Link
              href="/scan"
              className="inline-flex items-center justify-center gap-2.5 h-13 px-6 rounded-xl border border-black/20 bg-white/60 text-black font-medium text-sm hover:bg-white transition-all shadow-sm"
            >
              <QrCode className="size-4" />
              <span>Scan Equipment QR</span>
            </Link>
          </div>
        </div>

        {/* Right: Operational Mirror Card */}
        <GlassCard
          variant="light"
          hasCornerBrackets
          className="p-7 flex flex-col justify-between overflow-hidden relative"
        >
          {/* Top readout */}
          <div className="flex items-start justify-between">
            <div>
              <span className="text-xs font-semibold text-[#6a6a6a] uppercase tracking-wider block">
                Fleet Utilization
              </span>
              <p
                className="text-4xl sm:text-5xl font-medium tracking-tight text-black mt-1"
                style={{ fontFamily: "var(--font-playfair), Georgia, serif" }}
              >
                {fleetUtilizationPct === undefined ? "—" : `${fleetUtilizationPct}%`}
              </p>
            </div>
            <div className="flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>{fleetUtilizationPct === undefined ? "Loading" : "Fleet Snapshot"}</span>
            </div>
          </div>

          <div className="my-6 h-14 w-full flex items-center">
            <div className="h-3 w-full rounded-full bg-black/10" role="meter" aria-label="Fleet utilization"
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={fleetUtilizationPct}>
              <div className="h-3 rounded-full bg-[#ff5a24]" style={{ width: `${Math.max(0, Math.min(100, fleetUtilizationPct ?? 0))}%` }} />
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-black/10 text-xs">
            <div>
              <span className="text-[#7a7a7a] font-normal block">Average Fleet Utilization</span>
              <span className="font-semibold text-black text-base mt-0.5 block">{fleetUtilizationPct ?? "—"}%</span>
            </div>
            <div>
              <span className="text-[#7a7a7a] font-normal block">Active vs Surveillance</span>
              <span className="font-semibold text-black text-base mt-0.5 block">
                {activeAssets ?? "—"} / {totalAssets ?? "—"} Assets Active
              </span>
            </div>
          </div>
        </GlassCard>
      </div>
    </section>
  );
}
