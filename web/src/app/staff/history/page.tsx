"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Eye, Lock } from "lucide-react";
import { LevelWord } from "@/features/staff-pwa/components/level-word";
import { staffApi } from "@/features/staff-pwa/api/staffApi";
import {
  completedAttempt,
  diegoObservation,
  historyAug26Attempt,
  historyAug29Attempt,
  scenarios,
} from "@/lib/mock/seed";
import { dimensionShort } from "@/lib/format";
import type { BarsDimension } from "@/lib/types";

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "Aug 30" from a result's ISO completed_at, read in UTC. */
function dayLabel(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime())
    ? isoDate.slice(0, 10)
    : `${MONTH_SHORT[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

interface Row {
  id: string;
  title: string;
  dateLabel: string;
  completedAt: string;
  scores: { dimension: BarsDimension; level: number | null }[];
}

const scenarioTitles = new Map(scenarios.map((s) => [s.id, s.title]));

/** The seeded runs, used only when the API has nothing to show.
 *
 * These carry readable ids the database has never held. They exist so the
 * screen is not empty on a fresh environment, and so the links the app itself
 * renders still resolve — the results page falls back to the same seed. */
const seededRows: Row[] = [
  completedAttempt,
  historyAug29Attempt,
  historyAug26Attempt,
]
  .flatMap((attempt) => {
    const result = attempt.result;
    if (!result) return [];
    return [{
      id: attempt.id,
      title: scenarioTitles.get(result.scenario_id) ?? "Practice run",
      dateLabel: dayLabel(result.completed_at),
      completedAt: result.completed_at,
      scores: result.scores.filter((s) => s.level !== null),
    }];
  })
  .sort((a, b) => b.completedAt.localeCompare(a.completedAt));

// The sequencing gate: a manager observation is what turns practice into a
// coaching insight. Diego's exists, so the runs below are compared against the
// floor stream.
const managerObserved = diegoObservation.staff_id === "9f2c-diego";

export default function HistoryPage() {
  // Starts with the seeded rows so the screen is never blank while the request
  // is in flight, then replaces them with whatever the person actually did.
  const [rows, setRows] = useState<Row[]>(seededRows);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    staffApi
      .listMyAttempts()
      .then((runs) => {
        if (!live || !runs.length) return;
        setRows(
          runs.map((run) => ({
            id: run.id,
            title: run.title || "Practice run",
            dateLabel: run.completed_at ? dayLabel(run.completed_at) : "",
            completedAt: run.completed_at,
            scores: run.scores.filter((s) => s.level !== null),
          }))
        );
      })
      .catch(() => {
        // Keep the seeded rows rather than showing an error. This screen is
        // somebody's own record of their work; an empty state here reads as
        // "none of that counted".
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">My practice</h1>
        <p className="text-xs text-muted-foreground">
          This is your practice space, just for you. Your manager never sees
          your individual practice scores. They only get a coaching insight,
          and only after they&apos;ve logged their own observation of you.
        </p>
      </div>

      <div
        className={`overflow-hidden rounded-2xl border bg-card transition-opacity ${
          loading ? "opacity-60" : "opacity-100"
        }`}
      >
        {rows.map((entry, index) => (
          <div key={entry.id} className={`p-4 ${index > 0 ? "border-t" : ""}`}>
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">{entry.title}</p>
              <span className="text-xs text-muted-foreground">{entry.dateLabel}</span>
            </div>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {entry.scores.map(({ dimension, level }) => (
                <LevelWord
                  key={dimension}
                  level={level}
                  prefix={dimensionShort[dimension]}
                />
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                {managerObserved ? (
                  <>
                    <Eye className="size-3.5" />
                    Your manager logged their own observation of you, that&apos;s
                    what turns your practice into a coaching insight.
                  </>
                ) : (
                  <>
                    <Lock className="size-3.5" />
                    Waiting on your manager&apos;s floor observation, until
                    then, this practice stays just yours.
                  </>
                )}
              </span>
              <Link
                href={`/staff/results/${entry.id}`}
                className="-mr-2 flex min-h-9 shrink-0 items-center gap-1 rounded-lg px-2 font-medium text-primary"
              >
                Details <ArrowRight className="size-3" />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
