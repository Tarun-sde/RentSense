import { EquipmentStatus } from "@/types";

export const STATUS_CONFIG: Record<
  EquipmentStatus,
  {
    label: string;
    color: string;
    bgLight: string;
    borderLight: string;
    textColor: string;
    badgeBg: string;
    dotColor: string;
  }
> = {
  ACTIVE: {
    label: "Active",
    color: "#16a34a",
    bgLight: "bg-emerald-500/10",
    borderLight: "border-emerald-500/25",
    textColor: "text-emerald-700 dark:text-emerald-400",
    badgeBg: "bg-emerald-50 text-emerald-800 border-emerald-200",
    dotColor: "bg-emerald-500",
  },
  IDLE: {
    label: "Idle / Low Use",
    color: "#eab308",
    bgLight: "bg-amber-500/10",
    borderLight: "border-amber-500/25",
    textColor: "text-amber-700 dark:text-amber-400",
    badgeBg: "bg-amber-50 text-amber-800 border-amber-200",
    dotColor: "bg-amber-500",
  },
  DUE_SOON: {
    label: "Due Soon (<48h)",
    color: "#ff5a24",
    bgLight: "bg-[#ff5a24]/10",
    borderLight: "border-[#ff5a24]/30",
    textColor: "text-[#ff5a24]",
    badgeBg: "bg-orange-50 text-[#ff5a24] border-[#ff5a24]/30",
    dotColor: "bg-[#ff5a24]",
  },
  OVERDUE: {
    label: "Overdue",
    color: "#dc2626",
    bgLight: "bg-red-500/10",
    borderLight: "border-red-500/30",
    textColor: "text-red-700 dark:text-red-400",
    badgeBg: "bg-red-50 text-red-800 border-red-200",
    dotColor: "bg-red-600",
  },
  UNASSIGNED: {
    label: "Unassigned",
    color: "#64748b",
    bgLight: "bg-slate-500/10",
    borderLight: "border-slate-500/25",
    textColor: "text-slate-700 dark:text-slate-400",
    badgeBg: "bg-slate-100 text-slate-800 border-slate-300",
    dotColor: "bg-slate-400",
  },
};
