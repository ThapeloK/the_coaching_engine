import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScoreResults } from "@/features/staff-pwa/components/score-results";
import { staffApi } from "@/features/staff-pwa/api/staffApi";
import {
  completedAttempt,
  historyAug26Attempt,
  historyAug29Attempt,
  scenarios,
} from "@/lib/mock/seed";

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

export default async function ResultsPage(
  props: PageProps<"/staff/results/[id]">
) {
  const { id } = await props.params;

  // The practice history is seeded, because there is no endpoint that lists a
  // person's past attempts yet. Those rows carry readable ids the database has
  // never held, so ask the API first and fall back to the seed rather than
  // showing an error for a link the app itself rendered.
  const seeded = new Map(
    [completedAttempt, historyAug29Attempt, historyAug26Attempt].map(
      (a) => [a.id, a] as const
    )
  );

  // The API client throws on any non-2xx, including the 404 the API now
  // returns for an id it has never held. A missing attempt is an ordinary
  // outcome here, not a failure, so swallow it and let the seed answer.
  const fetched = await staffApi.getAttempt(id).catch(() => undefined);
  const attempt = fetched ?? seeded.get(id);
  const result = attempt?.result ?? null;
  const scenarioId = attempt?.scenario_id ?? result?.scenario_id ?? null;
  const scenario = scenarioId
    ? scenarios.find((s) => s.id === scenarioId)
    : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="size-8 shrink-0"
          nativeButton={false} render={<Link href="/staff/practice" />}
        >
          <ArrowLeft className="size-4" />
        </Button>
        <div>
          <p className="text-sm font-semibold">Your practice notes</p>
          <p className="text-xs text-muted-foreground">
            One read of the whole conversation, every label points back to
            your own words.
          </p>
          {result && (
            <p className="mt-0.5 text-xs font-medium text-primary">
              {scenario?.title ?? "Practice run"} ·{" "}
              {dayLabel(result.completed_at)}
            </p>
          )}
        </div>
      </div>

      {result ? (
        <ScoreResults result={result} />
      ) : (
        <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          This practice is still in progress, finish the conversation to see
          your notes.
        </p>
      )}

      <Button
        variant="outline"
        className="w-full"
        nativeButton={false} render={<Link href="/staff/practice" />}
      >
        Back to scenarios <ArrowRight className="size-4" />
      </Button>
    </div>
  );
}
