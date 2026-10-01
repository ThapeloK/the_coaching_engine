"use client";

import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ClipboardList,
  MessageSquareQuote,
  Radar,
  Target,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  citationKindLabel,
  classificationMeta,
  formatRate,
  primaryCalibration,
} from "@/lib/format";
import type { Citation, Recommendation } from "@/lib/types";

const citationIcons: Record<Citation["kind"], typeof MessageSquareQuote> = {
  attempt_turn: MessageSquareQuote,
  observation: ClipboardList,
  sop_chunk: BookOpen,
  rubric_anchor: Target,
  metric: Radar,
};

/** Label fallback for kinds the shared formatter has not been taught yet. */
const citationKindFallback: Partial<Record<Citation["kind"], string>> = {
  rubric_anchor: "Rubric anchor",
};

const classificationTone: Record<string, string> = {
  behavioural: "bg-[oklch(0.76_0.07_74)]/15 text-[oklch(0.45_0.07_72)] border-[oklch(0.76_0.07_74)]/30",
  process: "bg-[oklch(0.63_0.06_115)]/12 text-[oklch(0.43_0.06_115)] border-[oklch(0.63_0.06_115)]/30",
  policy: "bg-[oklch(0.66_0.09_30)]/12 text-[oklch(0.45_0.08_30)] border-[oklch(0.66_0.09_30)]/30",
};

interface MergedClaim {
  claim: string;
  kinds: Citation["kind"][];
  sources: Citation[];
}

/**
 * One row per claim, not one row per source.
 *
 * The agent emits a claim once per citation, so a claim supported by two
 * practice turns arrived as two identical sentences. Twelve of the sixteen
 * recommendations in the live queue read that way, which is the single biggest
 * reason this card looked long: a quarter of it was the same sentence twice.
 *
 * Merging is presentation only. Every source is kept and still opens.
 */
function mergeClaims(citations: Citation[]): MergedClaim[] {
  const byClaim = new Map<string, MergedClaim>();
  for (const c of citations) {
    const key = (c.claim || "").trim();
    const found = byClaim.get(key);
    if (found) {
      found.sources.push(c);
      if (!found.kinds.includes(c.kind)) found.kinds.push(c.kind);
    } else {
      byClaim.set(key, { claim: key, kinds: [c.kind], sources: [c] });
    }
  }
  return [...byClaim.values()];
}

function kindLabel(kind: Citation["kind"]): string {
  return (
    citationKindLabel[kind] ??
    citationKindFallback[kind] ??
    kind.replace("_", " ")
  );
}

export function RecommendationCard({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  // Shut by default. A manager deciding confirm or reject does not read the
  // evidence every time; they read it when something looks wrong. Leaving it
  // open put the longest block on the screen above the decision.
  const [showWhy, setShowWhy] = useState(false);
  const [showSay, setShowSay] = useState(false);
  const [openSource, setOpenSource] = useState<string | null>(null);

  // Both of these are absent on real data in ways the type did not admit: an
  // abstained recommendation has no classification, and calibration arrives as
  // an array. Resolve them once, here, instead of at four call sites.
  const meta = recommendation.classification
    ? classificationMeta[recommendation.classification]
    : null;
  const calibration = primaryCalibration(recommendation.calibration);
  const citations = recommendation.citations ?? [];
  const claims = mergeClaims(citations);

  return (
    <Card>
      <CardContent className="space-y-4 p-5 md:p-6">
        {/* ---------------------------------------------------- the verdict */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={
              recommendation.classification
                ? classificationTone[recommendation.classification]
                : undefined
            }
          >
            {meta ? meta.label : "Abstained"}
          </Badge>
          {meta && (
            <span className="text-xs text-muted-foreground">{meta.hint}</span>
          )}
          <span className="ml-auto text-xs tabular-nums text-muted-foreground/70">
            {recommendation.trace_id?.slice(0, 8)}
          </span>
        </div>

        <h2 className="text-lg font-semibold leading-snug md:text-xl">
          {recommendation.headline}
        </h2>

        {/* ------------------------------------------------------ the action */}
        {recommendation.suggested_action && (
          <div className="rounded-xl border border-primary/25 bg-accent/30 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              Do this
            </p>
            <p className="mt-1 text-sm font-medium leading-relaxed">
              {recommendation.suggested_action}
            </p>
          </div>
        )}

        {/* ------------------------------------- everything else, one tap away */}
        <div className="space-y-2">
          {recommendation.body && (
            <Disclosure
              open={showSay}
              onToggle={() => setShowSay((v) => !v)}
              label="What to say when you talk to them"
            >
              <p className="px-3 pb-3 text-sm leading-relaxed text-muted-foreground">
                {recommendation.body}
              </p>
            </Disclosure>
          )}

          {claims.length > 0 && (
            <Disclosure
              open={showWhy}
              onToggle={() => setShowWhy((v) => !v)}
              label={`Why it says this`}
              note={`${claims.length} claim${claims.length === 1 ? "" : "s"}, ${
                citations.length
              } source${citations.length === 1 ? "" : "s"}`}
            >
              <div className="space-y-2 px-3 pb-3">
                {claims.map((claim) => (
                  <div key={claim.claim} className="rounded-lg bg-muted/40 p-3">
                    <p className="text-sm leading-relaxed">{claim.claim}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {claim.sources.map((source) => {
                        const Icon = citationIcons[source.kind];
                        const isOpen = openSource === source.source_ref;
                        return (
                          <button
                            key={source.source_ref}
                            type="button"
                            onClick={() =>
                              setOpenSource(isOpen ? null : source.source_ref)
                            }
                            aria-expanded={isOpen}
                            className={`inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-xs transition-colors ${
                              isOpen
                                ? "border-primary/40 bg-accent/40 text-foreground"
                                : "bg-card text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            <Icon className="size-3.5 shrink-0" />
                            {kindLabel(source.kind)}
                          </button>
                        );
                      })}
                    </div>
                    {claim.sources
                      .filter(
                        (s) => openSource === s.source_ref && s.quoted_span
                      )
                      .map((s) => (
                        <div
                          key={s.source_ref}
                          className="mt-2 border-l-2 border-primary/30 pl-3"
                        >
                          <p className="text-xs leading-relaxed text-muted-foreground">
                            &ldquo;{s.quoted_span}&rdquo;
                          </p>
                          <p className="mt-1 text-[11px] tabular-nums text-muted-foreground/60">
                            {s.source_ref}
                          </p>
                        </div>
                      ))}
                  </div>
                ))}
              </div>
            </Disclosure>
          )}
        </div>

        {/* -------------------------------------------------- the small print */}
        {calibration && (
          <p className="text-xs text-muted-foreground">
            Agrees with your managers{" "}
            <span className="font-semibold text-foreground">
              {formatRate(calibration.agreement_rate)}
            </span>{" "}
            of the time on {calibration.dimension?.replace("_", " ")}, over{" "}
            {calibration.sample_size} check
            {calibration.sample_size === 1 ? "" : "s"}.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** A labelled row that opens. Same shape for both sections so the card has one
 * disclosure pattern rather than two that look almost alike. */
function Disclosure({
  open,
  onToggle,
  label,
  note,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  label: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`rounded-xl border ${open ? "bg-muted/20" : "bg-card"}`}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronDown
          className={`size-4 shrink-0 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
        {label}
        {note && (
          <span className="ml-auto text-xs font-normal text-muted-foreground/70">
            {note}
          </span>
        )}
      </button>
      {open && children}
    </div>
  );
}
