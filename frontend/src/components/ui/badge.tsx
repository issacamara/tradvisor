import React from "react";
import { cn } from "@/lib/utils";

type BadgeProps = { tone?: "positive" | "neutral" | "warning"; children: React.ReactNode };

export function Badge({ tone = "neutral", children }: BadgeProps) {
  const tones = {
    positive: "border-accent/50 bg-accent/10 text-accent",
    neutral: "border-line bg-white/5 text-muted",
    warning: "border-warning/50 bg-warning/10 text-warning",
  };
  return <span className={cn("inline-flex rounded border px-2 py-0.5 text-xs font-semibold", tones[tone])}>{children}</span>;
}
