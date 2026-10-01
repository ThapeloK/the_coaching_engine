"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  dimensionShort,
  observationDimensionLabels,
  quadrantMeta,
} from "@/lib/format";
import type { GapDimension, Quadrant, TransferGap } from "@/lib/types";

/** Quadrant badge tones — one per quadrant, keyed by the tone the dataset
 * rows already carry (see quadrantMeta in lib/format.ts). Muted warm family:
 * sage / caramel / terracotta / olive, tuned for the cream surface: tinted
 * chip fills with deep same-hue text, never light-on-light. */
const toneClasses: Record<string, { chip: string; text: string }> = {
  emerald: {
    chip: "bg-primary/10 text-primary border-primary/25",
    text: "text-primary",
  },
  amber: {
    chip: "bg-[oklch(0.76_0.07_74)]/15 text-[oklch(0.45_0.07_72)] border-[oklch(0.76_0.07_74)]/30",
    text: "text-[oklch(0.45_0.07_72)]",
  },
  rose: {
    chip: "bg-[oklch(0.66_0.09_30)]/12 text-[oklch(0.45_0.08_30)] border-[oklch(0.66_0.09_30)]/30",
    text: "text-[oklch(0.45_0.08_30)]",
  },
  olive: {
    chip: "bg-[oklch(0.63_0.06_115)]/12 text-[oklch(0.43_0.06_115)] border-[oklch(0.63_0.06_115)]/30",
    text: "text-[oklch(0.43_0.06_115)]",
  },
};

/** Recalibrate arrives as "violet" in quadrantMeta while its badge renders
 * olive; unknown keys fall back to olive instead of breaking the rows. */
const toneFor = (tone: string) => toneClasses[tone] ?? toneClasses.olive;

/** One-line conclusion per quadrant for the top card. The four readings
 * follow the quadrant semantics the dataset rows already carry — the copy
 * stays fixed so the card reads the same way for every staff member. */
const conclusionLine: Record<Quadrant, string> = {
  blocked:
    "Practice is strong but the floor is not. This reads as a systems gap, not a skill gap.",
  skill_gap:
    "Floor trails practice. This reads as a coaching gap, not a policy gap.",
  competent: "Floor matches practice. No transfer gap on the scored dimensions.",
  recalibrate:
    "Floor runs ahead of practice. Worth checking the standard.",
};

/** One-line qualitative reading per quadrant for the dimension rows. The
 * rows carry the coaching recommendation, never the numbers behind it. */
const quadrantLine: Record<Quadrant, string> = {
  blocked: "Practice looks fine, the floor doesn't match.",
  skill_gap: "The floor is trailing practice.",
  competent: "Floor matches practice.",
  recalibrate: "The floor runs ahead of practice.",
};

/** The dimension that sets the page's overall reading: a blocked finding
 * outranks everything, then the largest practice→floor gap — the same
 * preference db.ts applies when it picks the primary gap for a
 * recommendation. The row order is frozen, so ties resolve deterministically. */
function overallReading(
  dimensions: TransferGap["dimensions"]
): GapDimension | undefined {
  if (dimensions.length === 0) return undefined;
  return [...dimensions].sort((a, b) => {
    const aBlocked = a.quadrant === "blocked" ? 0 : 1;
    const bBlocked = b.quadrant === "blocked" ? 0 : 1;
    if (aBlocked !== bBlocked) return aBlocked - bBlocked;
    return b.gap - a.gap;
  })[0];
}


/** BARS runs 1 to 5, so a level sits at (v - 1) / 4 along the track. */
const pos = (v: number) => `${Math.max(0, Math.min(1, (v - 1) / 4)) * 100}%`;

/**
 * Practice and floor on one track, with the distance between them drawn.
 *
 * The length of the connecting line is the transfer gap. Nothing has to be
 * read to see that two dots are far apart, which is the point: a manager
 * scanning five rows finds the problem before they have read a single word.
 */
function GapTrack({
  practice,
  floor,
}: {
  practice: number;
  floor: number;
}) {
  const lo = Math.min(practice, floor);
  const hi = Math.max(practice, floor);
  return (
    <div className="relative h-6 w-full" aria-hidden>
      {/* the 1 to 5 track */}
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
      {/* the gap */}
      <div
        className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-[oklch(0.76_0.07_74)]/45"
        style={{ left: pos(lo), right: `calc(100% - ${pos(hi)})` }}
      />
      {/* floor first, so practice sits on top where they overlap */}
      <span
        className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-[oklch(0.55_0.09_60)]"
        style={{ left: pos(floor) }}
      />
      <span
        className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary"
        style={{ left: pos(practice) }}
      />
    </div>
  );
}

export function GapQuadrant({
  gap,
  staffName,
}: {
  gap: TransferGap;
  staffName: string;
}) {
  const firstName = staffName.split(" ")[0];
  const lead = overallReading(gap.dimensions);
  const [selected, setSelected] = useState(gap.dimensions[0]?.dimension);
  const active =
    gap.dimensions.find((d) => d.dimension === selected) ?? gap.dimensions[0];
  const leadTone = lead ? toneFor(quadrantMeta[lead.quadrant].tone) : null;

  return (
    <div className="space-y-6">
      {/* Conclusion card: the reading a manager walks away with. The lead
          dimension picks the quadrant line; the opening stays fixed. */}
      <section className="rounded-xl border bg-card p-5">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Practice shows what {firstName} can do. The floor shows what{" "}
          {firstName} actually did. When the floor falls behind, the answer
          usually isn&apos;t more training.
        </p>
        {lead && (
          <p
            className={`mt-3 text-base font-semibold leading-snug ${
              leadTone ? leadTone.text : "text-foreground"
            }`}
          >
            {conclusionLine[lead.quadrant]}
          </p>
        )}
      </section>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <CardTitle className="text-base">Scored dimensions</CardTitle>
            <span className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-primary" />
                practice
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-[oklch(0.55_0.09_60)]" />
                floor
              </span>
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            The bar between the two dots is the gap. Longest first. Select a
            row for the evidence behind it.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          {[...gap.dimensions]
            .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))
            .map((d) => (
            <button
              key={d.dimension}
              type="button"
              onClick={() => setSelected(d.dimension)}
              aria-pressed={selected === d.dimension}
              className={`flex w-full items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition-colors ${
                selected === d.dimension
                  ? "border-primary bg-accent/30"
                  : "bg-card hover:bg-muted/40"
              }`}
            >
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="truncate text-sm font-semibold">
                    {dimensionShort[d.dimension]}
                  </span>
                  <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
                    {d.practice_mean?.toFixed(1)}
                    <span className="mx-1 text-muted-foreground/50">vs</span>
                    {d.floor_mean?.toFixed(1)}
                  </span>
                </span>
                <GapTrack
                  practice={d.practice_mean ?? 1}
                  floor={d.floor_mean ?? 1}
                />
                <span className="block text-xs text-muted-foreground">
                  {quadrantLine[d.quadrant]}
                </span>
              </span>
              <Badge
                variant="outline"
                className={`shrink-0 ${toneFor(quadrantMeta[d.quadrant].tone).chip}`}
              >
                {quadrantMeta[d.quadrant].label}
              </Badge>
            </button>
          ))}

          {active && (
            <div
              key={active.dimension}
              className="msg-in rounded-xl border bg-muted/40 p-4"
            >
              <p className="text-sm font-semibold">
                {dimensionShort[active.dimension]},{" "}
                <span
                  className={toneFor(quadrantMeta[active.quadrant].tone).text}
                >
                  {quadrantMeta[active.quadrant].label}
                </span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {active.reading}
              </p>
            </div>
          )}

          {gap.insufficient_evidence.length > 0 && (
            <p className="rounded-xl border border-dashed p-3 text-xs text-muted-foreground">
              No floor observations yet for{" "}
              {gap.insufficient_evidence
                .map((d) => observationDimensionLabels[d])
                .join(", ")}
              . The gap is left unscored rather than guessed.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
