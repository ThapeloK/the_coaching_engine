"use client";

import { Check } from "lucide-react";
import type { BarsDimension } from "@/lib/types";

/**
 * BARS rubric anchors rendered as tappable description rows instead of
 * number buttons — one row per level, index 0 = level 1 at the top, so the
 * row a manager taps IS the level (row 3 → level 3). No numbers are shown
 * anywhere in this surface. Wordings are verbatim from the calibration
 * standard — team lead: "use exactly as is".
 */
const BARS_LEVEL_DESCRIPTIONS: Record<BarsDimension, readonly string[]> = {
  empathy: [
    "Ignored what the guest said, deflected",
    "Minimal acknowledgement, no ownership shown",
    "Acknowledged the feeling, handed off without owning it",
    "Repeated the concern back, took personal ownership",
    "Used guest context, committed to following up personally",
  ],
  anticipation: [
    "Only reacted, or assumed without checking",
    "Noticed a signal, didn't act on it",
    "Met the stated need, nothing beyond it",
    "Spotted one unspoken need, offered to help",
    "Read multiple signals, acted before being asked",
  ],
  communication: [
    "Blunt or negative",
    "Short and functional, no warmth",
    "Polite and correct, but generic",
    "Consistently warm, used guest's name naturally",
    "Matched the guest's tone, personal sign-off",
  ],
  composure: [
    "Defensive, blamed someone else",
    "Short and clipped, strain showed",
    "Professional, but not reassuring",
    "Calm and steady, took ownership",
    "Fully in control, reassured the guest",
  ],
  service_recovery: [
    "Problem left unresolved",
    "Vague fix, no clear commitment",
    "Direct fix, matched the problem",
    "Fully resolved, personal ownership shown",
    "Resolved, added a gesture, confirmed follow-up",
  ],
};

const ROW_IDLE =
  "border bg-card text-foreground hover:bg-muted/40";
const ROW_SELECTED =
  "border-primary bg-primary text-primary-foreground";

export function BarsLevelPicker({
  dimension,
  value,
  onChange,
  label = "BARS level",
}: {
  dimension: BarsDimension;
  value: number | null;
  onChange: (level: number) => void;
  label?: string;
}) {
  const rows = BARS_LEVEL_DESCRIPTIONS[dimension];
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="space-y-1.5"
    >
      {rows.map((description, index) => {
        const level = index + 1;
        const selected = value === level;
        return (
          <button
            key={description}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(level)}
            className={`flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm leading-snug transition-colors ${
              selected ? ROW_SELECTED : ROW_IDLE
            }`}
          >
            <span className="min-w-0 flex-1">{description}</span>
            {selected && <Check className="size-4 shrink-0" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}
