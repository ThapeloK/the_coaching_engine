"use client";

import { useState } from "react";
import { ChevronDown, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CountUp } from "@/components/count-up";
import type { CalibrationState } from "@/lib/types";

/** One plain sentence per state — shown when the reading list carries no
 * advice of its own (LLD-D §5.3: managers read percentages, not scores). */
const stateSentence: Record<CalibrationState, string> = {
  unmeasured: "Not measured yet on this dimension.",
  provisional: "Early days, only a handful of checks so far.",
  reliable: "Agreement is reliably high on this dimension.",
  uncertain: "Still settling, keep verifying on this dimension.",
  unreliable: "Treat this read with caution for now.",
};

export interface CalibrationSummary {
  rate: number | null;
  dimensionCount: number;
  sampleSize: number;
  state: CalibrationState | null;
  advice: string | null;
}

/** Calibration compact card. The default view carries one plain sentence —
 * the percentage, sample line and verdict state wait behind Details so the
 * overview reads like a person, not a dashboard. */
export function CalibrationCard({
  summary,
}: {
  summary: CalibrationSummary | null;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="fade-up [animation-delay:240ms]">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ShieldCheck className="size-4 text-primary" />
          Calibration · overall agreement
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          How often the agent&apos;s read matches your verdicts.
        </p>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="calibration-details"
          onClick={() => setOpen((o) => !o)}
          className="mt-3 inline-flex min-h-9 items-center gap-1 rounded-full border border-dashed px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          Details
          <ChevronDown
            className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
        {open && (
          <div id="calibration-details" className="msg-in mt-3 space-y-1">
            <p className="text-3xl font-bold tabular-nums">
              {summary?.rate != null ? (
                <>
                  <CountUp value={summary.rate * 100} decimals={1} />
                  %
                </>
              ) : (
                "–"
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {summary
                ? `mean across ${summary.dimensionCount} dimensions · n = ${summary.sampleSize}`
                : "no verified verdicts yet"}
            </p>
            {summary?.advice && (
              <p className="text-xs text-muted-foreground">{summary.advice}</p>
            )}
            {summary?.state && summary.state !== "unmeasured" && (
              <p className="text-xs font-medium text-primary">
                {stateSentence[summary.state]}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Watch the calibration number move, live.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
