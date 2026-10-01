"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, FilterX, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { VerifyQueueCard } from "./verify-queue-card";
import { dimensionShort, primaryCalibration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { BarsDimension, Recommendation } from "@/lib/types";

export interface VerifyQueueEntry {
  recommendation: Recommendation;
  staffName: string;
}

/** Chips follow the canonical BARS order, showing only dimensions that
 * actually appear in the queue. */
const DIMENSION_ORDER: BarsDimension[] = [
  "service_recovery",
  "empathy",
  "communication",
  "composure",
  "anticipation",
];

type QueueFilter =
  | { kind: "all" }
  | { kind: "abstained" }
  | { kind: "dimension"; dimension: BarsDimension };

const chipClasses = (active: boolean) =>
  cn(
    "inline-flex min-h-10 items-center rounded-full px-3.5 text-xs font-medium transition-colors",
    active
      ? "bg-primary text-primary-foreground"
      : "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground"
  );

/**
 * The interactive verify queue: filter chips on top, inline expansion per
 * card, and local removal once a verdict is recorded. All state updates are
 * immutable — rows are filtered into new arrays, never mutated in place.
 */

/** How the classification reads to a manager, in the plural. */
const PATTERN_COPY: Record<string, { label: string; meaning: string }> = {
  policy: {
    label: "policy",
    meaning:
      "the same missing authority. That is one policy to write, not one conversation each.",
  },
  process: {
    label: "process",
    meaning:
      "the same workflow problem. Coaching each person leaves the workflow in place.",
  },
  behavioural: {
    label: "behavioural",
    meaning:
      "individual coaching is the right route for each of these.",
  },
};

/**
 * Named above the list, not buried in it.
 *
 * A queue of eleven reads as eleven jobs. When most of them carry the same
 * classification they are usually one job, and a duty manager with ten minutes
 * should be told that before they start working down the list. Only fires at
 * three or more, because two of a kind is a coincidence.
 */
function PatternBand({ pending }: { pending: Recommendation[] }) {
  const counts = new Map<string, number>();
  for (const r of pending) {
    if (!r.classification) continue;
    counts.set(r.classification, (counts.get(r.classification) ?? 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top || top[1] < 3) return null;

  const [kind, n] = top;
  const copy = PATTERN_COPY[kind];
  if (!copy) return null;

  // Rows are not people. Diego alone accounts for four of the pending reads,
  // so counting rows and calling them people overstates how many staff are
  // affected, on the one screen that must not overstate anything.
  const people = new Set(
    pending.filter((r) => r.classification === kind).map((r) => r.staff_id)
  ).size;

  return (
    <div className="msg-in rounded-xl border border-primary/25 bg-accent/30 p-4">
      <div className="flex items-start gap-3">
        <Users className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">
            {n} of these {n === pending.length ? "" : `${pending.length} `}say
            the same thing
          </p>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            {people} {people === 1 ? "person" : "people"}, {copy.meaning}
          </p>
          <Link
            href="/manager/insights"
            className="mt-2 inline-flex min-h-9 items-center gap-1.5 text-sm font-medium text-primary hover:underline"
          >
            See it as a team pattern
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}

export function VerifyQueue({ entries }: { entries: VerifyQueueEntry[] }) {
  const [items, setItems] = useState<VerifyQueueEntry[]>(entries);
  const [filter, setFilter] = useState<QueueFilter>({ kind: "all" });
  const [openId, setOpenId] = useState<string | null>(null);

  const pending = items.filter(
    (entry) => entry.recommendation.status === "pending_verify"
  );
  const hasAbstained = items.some(
    (entry) => entry.recommendation.status === "abstained"
  );

  const dimensionChips = useMemo(() => {
    const present = new Set(
      items.map(
        (entry) =>
          primaryCalibration(entry.recommendation.calibration)?.dimension
      )
    );
    return DIMENSION_ORDER.filter((dimension) => present.has(dimension));
  }, [items]);

  const visible = useMemo(() => {
    if (filter.kind === "abstained") {
      return items.filter(
        (entry) => entry.recommendation.status === "abstained"
      );
    }
    if (filter.kind === "dimension") {
      return items.filter(
        (entry) =>
          primaryCalibration(entry.recommendation.calibration)?.dimension ===
          filter.dimension
      );
    }
    return items;
  }, [items, filter]);

  const handleToggle = (id: string) => {
    setOpenId((open) => (open === id ? null : id));
  };

  const handleVerified = (id: string) => {
    setItems((prev) => prev.filter((entry) => entry.recommendation.id !== id));
    setOpenId((open) => (open === id ? null : open));
  };

  // "New" rides the first pending recommendation of the queue, regardless of
  // the active filter.
  const firstPendingId = pending[0]?.recommendation.id ?? null;

  if (items.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="size-5 text-primary" />
            Queue clear
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Every recommendation has a verdict. New drafts appear here as
            observations come in.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div
        role="group"
        aria-label="Filter the queue"
        className="msg-in flex flex-wrap items-center gap-2"
      >
        <button
          type="button"
          aria-pressed={filter.kind === "all"}
          className={chipClasses(filter.kind === "all")}
          onClick={() => setFilter({ kind: "all" })}
        >
          All
        </button>
        {dimensionChips.map((dimension) => {
          const active =
            filter.kind === "dimension" && filter.dimension === dimension;
          return (
            <button
              key={dimension}
              type="button"
              aria-pressed={active}
              className={chipClasses(active)}
              onClick={() => setFilter({ kind: "dimension", dimension })}
            >
              {dimensionShort[dimension]}
            </button>
          );
        })}
        {hasAbstained && (
          <button
            type="button"
            aria-pressed={filter.kind === "abstained"}
            className={chipClasses(filter.kind === "abstained")}
            onClick={() => setFilter({ kind: "abstained" })}
          >
            Abstained
          </button>
        )}
      </div>

      <PatternBand
        pending={items
          .filter((e) => e.recommendation.status === "pending_verify")
          .map((e) => e.recommendation)}
      />

      <div className="space-y-3">
        {visible.map((entry, index) => (
          <VerifyQueueCard
            key={entry.recommendation.id}
            recommendation={entry.recommendation}
            staffName={entry.staffName}
            isNew={entry.recommendation.id === firstPendingId}
            expanded={openId === entry.recommendation.id}
            index={index}
            onToggle={() => handleToggle(entry.recommendation.id)}
            onVerified={() => handleVerified(entry.recommendation.id)}
          />
        ))}

        {visible.length === 0 && (
          <Card className="fade-up [animation-delay:120ms]">
            <CardContent className="flex items-center gap-3 p-4 md:p-5">
              <FilterX
                className="size-5 shrink-0 text-muted-foreground"
                aria-hidden
              />
              <p className="text-sm text-muted-foreground">
                No recommendations match this filter.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
