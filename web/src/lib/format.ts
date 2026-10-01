import type {
  CalibrationInfo,
  BarsDimension,
  Classification,
  ObservationDimension,
  Quadrant,
} from "@/lib/types";

export const dimensionLabels: Record<BarsDimension, string> = {
  empathy: "Empathy & Active Listening",
  anticipation: "Guest Anticipation",
  communication: "Guest Communication",
  composure: "Composure & Professionalism",
  service_recovery: "Service Recovery",
};

export const observationDimensionLabels: Record<ObservationDimension, string> =
  {
    ...dimensionLabels,
  };

/** Display name plus the plain-English line the manager rates against, one
 * dimension at a time (observation wizard). Keyed by the canonical BARS key. */
export const observationDimensionLines: Record<
  BarsDimension,
  { name: string; line: string }
> = {
  service_recovery: {
    name: "Service Recovery",
    line: "Did they fix the problem for the guest?",
  },
  empathy: {
    name: "Empathy & Active Listening",
    line: "Did they acknowledge how the guest felt?",
  },
  communication: {
    name: "Guest Communication",
    line: "Did they explain things clearly and warmly?",
  },
  composure: {
    name: "Composure & Professionalism",
    line: "Did they stay calm and in control?",
  },
  anticipation: {
    name: "Guest Anticipation",
    line: "Did they spot what the guest needed before being asked?",
  },
};

export const dimensionShort: Record<BarsDimension, string> = {
  empathy: "Empathy",
  anticipation: "Anticipation",
  communication: "Communication",
  composure: "Composure",
  service_recovery: "Recovery",
};

/** One qualitative word per level — the only vocabulary staff-facing surfaces
 * may use for a level. Numeric levels stay manager-side. */
export const levelLabels: Record<number, string> = {
  1: "Finding this hard",
  2: "Early days",
  3: "Getting there",
  4: "Confident here",
  5: "Leading here",
};

/** The qualitative word for a scored level, or null when the dimension was
 * not scored. */
export function levelWord(level: number | null): string | null {
  return level === null || level < 1 || level > 5 ? null : levelLabels[level];
}

export interface QuadrantMeta {
  label: string;
  headline: string;
  reading: string;
  tone: string;
}

export const quadrantMeta: Record<Quadrant, QuadrantMeta> = {
  competent: {
    label: "No gap",
    headline: "Strong in practice and on the floor.",
    reading: "Stretch them. Promote. Use as a peer coach.",
    tone: "emerald",
  },
  skill_gap: {
    label: "Needs practice",
    headline: "Weak in both.",
    reading:
      "Targeted practice, the only quadrant where a simulation is the right answer.",
    tone: "amber",
  },
  blocked: {
    label: "Blocked",
    headline: "Knows how, held back on the floor.",
    reading:
      "They know how. Something is stopping them: pressure, time, unclear authority. Do NOT send more training.",
    tone: "rose",
  },
  recalibrate: {
    label: "Check the standard",
    headline: "Strong floor, weak practice.",
    reading:
      "Rubric or scenario mismatch, or they compensate with charm. A signal about our scoring, not about them.",
    tone: "violet",
  },
};

export const classificationMeta: Record<
  Classification,
  { label: string; hint: string }
> = {
  behavioural: {
    label: "Behavioural",
    hint: "Individual coaching is the right route.",
  },
  process: {
    label: "Process",
    hint: "Individual coaching is suppressed, fix the workflow.",
  },
  policy: {
    label: "Policy",
    hint: "The rules, not the person, are the blocker.",
  },
};

export const citationKindLabel: Record<string, string> = {
  attempt_turn: "Practice turn",
  observation: "Floor observation",
  sop_chunk: "Hotel standard",
  metric: "Transfer-gap metric",
};

export function formatRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

export function formatGap(gap: number): string {
  return gap > 0 ? `+${gap.toFixed(1)}` : gap.toFixed(1);
}

/**
 * One calibration reading from whatever shape the caller was handed.
 *
 * `GET /recommendations` returns `calibration` as an array of readings, one per
 * scored dimension. The mock returns a single object. Dereferencing the array
 * gives undefined, and the first `.replace()` on it takes the whole page down,
 * which is exactly what happened when a manager opened "Why is the AI saying
 * this?". Returns null rather than throwing when there is nothing to show.
 */
export function primaryCalibration(
  calibration: CalibrationInfo | CalibrationInfo[] | null | undefined
): CalibrationInfo | null {
  if (!calibration) return null;
  if (Array.isArray(calibration)) return calibration[0] ?? null;
  return calibration;
}
