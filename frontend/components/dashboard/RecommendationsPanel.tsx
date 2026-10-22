"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles, CheckCircle2, Zap } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { Recommendation } from "@/types";
import { triggerActionFromRecommendation } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface RecommendationsPanelProps {
  recommendations?: Recommendation[];
  onActionTriggered?: () => void;
}

export function RecommendationsPanel({
  recommendations = [],
  onActionTriggered,
}: RecommendationsPanelProps) {
  const router = useRouter();
  const [submittingId, setSubmittingId] = useState<number | null>(null);

  const totalAvoidableCost = recommendations.reduce((acc, r) => {
    return acc + (r.estimated_impact?.estimated_savings_usd || 0);
  }, 0);

  const handleExecuteAction = async (rec: Recommendation) => {
    try {
      setSubmittingId(rec.id);
      await triggerActionFromRecommendation(rec.id, {
        action_type: rec.recommendation_type,
        notes: `Initiated from Control Tower Dashboard: ${rec.action}`,
        actor: "Fleet Operator",
        payload: rec.estimated_impact || {},
      });
      if (onActionTriggered) {
        onActionTriggered();
      }
      router.push("/actions");
    } catch (err: unknown) {
      alert(`Error triggering action: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSubmittingId(null);
    }
  };

  return (
    <GlassCard variant="light" className="p-7 flex flex-col justify-between h-full">
      {/* Header */}
      <div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-[#ff5a24]" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
              Decision &amp; Action Queue
            </h3>
          </div>
          <span className="text-xs font-mono text-[#ff5a24] font-semibold bg-orange-50 px-2.5 py-0.5 rounded-full border border-[#ff5a24]/30">
            {formatCurrency(totalAvoidableCost)} Avoidable Cost
          </span>
        </div>
        <p className="text-xs text-[#6a6a6a] mt-1">
          Ranked cost avoidance &amp; fleet optimization recommendations
        </p>
      </div>

      {/* Cards List */}
      <div className="mt-5 space-y-3.5">
        {recommendations.length === 0 ? (
          <div className="py-8 text-center text-xs text-[#7a7a7a]">
            <CheckCircle2 className="size-6 text-emerald-500 mx-auto mb-2" />
            All fleet assets optimal. No pending optimization recommendations.
          </div>
        ) : (
          recommendations.slice(0, 3).map((rec) => {
            const savings = rec.estimated_impact?.estimated_savings_usd || 0;
            return (
              <div
                key={rec.id}
                className="rounded-xl border border-black/10 bg-white/70 p-4 shadow-sm hover:shadow-md transition-all group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/assets/${rec.equipment_id}`}
                        className="font-bold text-xs text-[#ff5a24] hover:underline"
                      >
                        {rec.equipment_id}
                      </Link>
                      <span className="text-xs font-semibold text-black">{rec.action}</span>
                    </div>
                    <p className="text-xs text-[#555555] mt-1 leading-snug">
                      {rec.explanation}
                    </p>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="text-xs font-bold text-emerald-700 block font-mono">
                      +{formatCurrency(savings)}
                    </span>
                    <span className="text-[10px] text-[#7a7a7a] block mt-0.5">
                      {Math.round(rec.confidence * 100)}% Conf.
                    </span>
                  </div>
                </div>

                {/* Action Bar */}
                <div className="mt-3 pt-2.5 border-t border-black/5 flex items-center justify-between text-xs">
                  <span className="text-[11px] text-[#7a7a7a] font-mono uppercase font-semibold">
                    Action: {rec.recommendation_type}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleExecuteAction(rec)}
                      disabled={submittingId === rec.id}
                      className="inline-flex items-center gap-1 px-3 py-1 rounded-lg text-[11px] font-medium bg-[#111111] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] hover:bg-black transition-all disabled:opacity-50"
                    >
                      <Zap className="size-3 text-[#ff5a24]" />
                      <span>{submittingId === rec.id ? "Queuing..." : "Execute Action"}</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer Link */}
      <div className="mt-4 pt-3 border-t border-black/10 flex items-center justify-between text-xs text-[#6a6a6a]">
        <span>Decision Engine Synchronized</span>
        <Link href="/actions" className="text-[#ff5a24] font-medium hover:underline">
          View Complete Action Queue ({recommendations.length}) →
        </Link>
      </div>
    </GlassCard>
  );
}
