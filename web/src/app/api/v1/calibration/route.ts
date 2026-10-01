import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";
import type { CalibrationReading, CalibrationState } from "@/lib/types";

/**
 * GET /calibration → bare array of contract `Calibration` rows
 * (openapi.yaml). The mock store keeps a computed_at wrapper internally
 * (db.ts/seed.ts are owned elsewhere); this route maps to the frozen shape
 * on the way out.
 */

// Canonical thresholds — mirror services/agent/coaching_engine/calibration.py.
const PROVISIONAL_BELOW_N = 10;
const RELIABLE_LOWER_BOUND = 0.75; // on the interval lower bound, not the point estimate
const UNRELIABLE_UPPER_BOUND = 0.65;

function stateOf(
  sampleSize: number,
  lower: number,
  upper: number
): CalibrationState {
  if (sampleSize < PROVISIONAL_BELOW_N) return "provisional";
  if (lower >= RELIABLE_LOWER_BOUND) return "reliable";
  if (upper < UNRELIABLE_UPPER_BOUND) return "unreliable";
  return "uncertain";
}

/** The sentence a manager actually reads (calibration.py `Calibration.display`). */
function adviceOf(
  state: CalibrationState,
  agreementRate: number | null,
  sampleSize: number
): string {
  const pct = Math.round((agreementRate ?? 0) * 100);
  switch (state) {
    case "provisional":
      return `Agrees with your managers ${pct}% of the time so far, on only ${sampleSize} checks.`;
    case "unreliable":
      return `Agrees with your managers ${pct}% of the time on this dimension. Treat with caution. We route these to a human first.`;
    case "uncertain":
      return `Agrees with your managers ${pct}% of the time (${sampleSize} checks). Still settling.`;
    case "unmeasured":
      return "Not yet measured on this dimension.";
    default:
      return `Agrees with your managers ${pct}% of the time (${sampleSize} checks).`;
  }
}

export async function GET() {
  try {
    const legacy = await mockDb.getCalibration();
    const readings: CalibrationReading[] = legacy.dimensions.map((d) => {
      const lower = d.lower ?? d.wilson_low;
      const upper = d.upper ?? d.wilson_high;
      // db.ts already stores canonical state/advice; derive as a fallback
      // only so the route survives any future mock refactor.
      const state = d.state ?? stateOf(d.sample_size, lower, upper);
      return {
        dimension: d.dimension,
        agreement_rate: d.agreement_rate,
        lower,
        upper,
        sample_size: d.sample_size,
        state,
        advice: d.advice ?? adviceOf(state, d.agreement_rate, d.sample_size),
      };
    });
    return NextResponse.json(readings);
  } catch (error) {
    console.error("Failed to read calibration:", error);
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Internal error",
        status: 500,
        detail: "Could not read calibration right now",
      },
      { status: 500, headers: { "Content-Type": "application/problem+json" } }
    );
  }
}
