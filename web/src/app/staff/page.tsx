import Link from "next/link";
import { ArrowRight, TrendingUp } from "lucide-react";
import { DebriefEntry } from "@/features/staff-pwa/components/debrief-entry";
import { LevelWord } from "@/features/staff-pwa/components/level-word";
import { diegoScoreResult } from "@/lib/mock/seed";
import { dimensionShort } from "@/lib/format";


/** Rendered per request, never prerendered.
 *
 * Without this Next may statically render at build time and the page freezes
 * with whatever the database held during deployment. Everything here is live
 * operational data, and a manager acting on a stale queue is worse than a
 * manager waiting a moment for a fresh one.
 */
export const dynamic = "force-dynamic";

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "Aug 30" from the result's ISO completed_at, read in UTC. */
function dayLabel(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime())
    ? isoDate.slice(0, 10)
    : `${MONTH_SHORT[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

export default function StaffHomePage() {
  const lastScore = diegoScoreResult;
  const lastRunDay = dayLabel(diegoScoreResult.completed_at);

  return (
    <div className="space-y-5">
      <h1 className="font-heading text-2xl font-semibold tracking-tight">
        Your practice
      </h1>
      <DebriefEntry />

      <div className="rounded-2xl border bg-card p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Your last practice</p>
          <Link
            href="/staff/history"
            className="-mr-2 flex min-h-9 items-center gap-1 rounded-lg px-2 text-xs font-medium text-primary"
          >
            All practice <ArrowRight className="size-3" />
          </Link>
        </div>
        <div className="mt-3 space-y-2">
          {lastScore.scores.slice(0, 3).map(({ dimension, level }) => (
            <div key={dimension} className="flex items-center gap-3">
              <LevelWord level={level} />
              <p className="min-w-0 flex-1 truncate text-sm">
                {dimensionShort[dimension]}
              </p>
              <span className="shrink-0 text-xs text-muted-foreground">
                {lastRunDay}
              </span>
            </div>
          ))}
        </div>
        <Link
          href="/staff/results/8a4e-diego"
          className="mt-3 flex items-center justify-between rounded-xl bg-accent/40 px-4 py-3 text-sm font-medium text-primary"
        >
          <span className="flex items-center gap-2">
            <TrendingUp className="size-4" />
            See what earned those labels
          </span>
          <ArrowRight className="size-4" />
        </Link>
      </div>

      <p className="text-center text-xs leading-relaxed text-muted-foreground">
        This is your practice space, just for you. Your manager never sees
        your individual practice scores. They only get a coaching insight, and
        only after they&apos;ve logged their own observation of you.
      </p>
    </div>
  );
}
