"use client";

import { useState } from "react";
import { ChevronDown, Quote } from "lucide-react";
import { LevelWord } from "@/features/staff-pwa/components/level-word";
import { dimensionLabels } from "@/lib/format";
import type { ScoreResult } from "@/lib/types";

export function ScoreResults({ result }: { result: ScoreResult }) {
  const [openDim, setOpenDim] = useState<string | null>(
    result.evidence[0]?.dimension ?? null
  );

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border bg-card p-4 text-center">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          In one read
        </p>
        <p className="mt-1 text-sm leading-relaxed">{result.overall_feedback}</p>
      </div>

      {result.scores.map(({ dimension, level }) => {
        const evidence = result.evidence.filter(
          (e) => e.dimension === dimension
        );
        const open = openDim === dimension;
        return (
          <div key={dimension} className="rounded-2xl border bg-card p-4">
            <button
              type="button"
              onClick={() => setOpenDim(open ? null : dimension)}
              className="flex w-full items-center gap-3 text-left"
            >
              <LevelWord level={level} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">
                  {dimensionLabels[dimension]}
                </p>
              </div>
              <ChevronDown
                className={`size-4 shrink-0 text-muted-foreground transition-transform ${
                  open ? "rotate-180" : ""
                }`}
              />
            </button>

            {open && evidence.length > 0 && (
              <div className="mt-3 space-y-2 border-t pt-3">
                {evidence.map((ev) => (
                  <div key={ev.turn_index} className="rounded-xl bg-muted/40 p-3">
                    <p className="flex items-center gap-1.5 text-xs font-semibold">
                      <Quote className="size-3.5 text-primary" />
                      What earned this, your own words
                    </p>
                    <p className="mt-1.5 text-xs italic leading-relaxed text-muted-foreground">
                      “{ev.quote}”
                    </p>
                    <p className="mt-2 text-xs leading-relaxed">
                      {ev.explains}
                    </p>
                  </div>
                ))}
              </div>
            )}
            {open && evidence.length === 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                No words captured for this one, it stays without a label
                rather than guessed.
              </p>
            )}
          </div>
        );
      })}

      <div className="rounded-2xl border border-dashed p-4">
        <p className="text-xs text-muted-foreground">
          This is your practice space, just for you. Your manager never sees
          your individual practice scores. They only get a coaching insight,
          and only after they&apos;ve logged their own observation of you.
        </p>
      </div>
    </div>
  );
}
