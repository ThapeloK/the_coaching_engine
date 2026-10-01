import Link from "next/link";
import {
  ArrowRight,
  ClipboardCheck,
  ListChecks,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RadarChart } from "@/components/ui/radar-chart";
import {
  CalibrationCard,
  type CalibrationSummary,
} from "@/features/manager-console/components/calibration-card";
import { RadarCaption } from "@/features/manager-console/components/radar-caption";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { staffMembers } from "@/lib/mock/seed";

import { dimensionLabels, dimensionShort } from "@/lib/format";
import type { BarsDimension, CalibrationReading, TransferGap } from "@/lib/types";


/** Rendered per request, never prerendered.
 *
 * Without this Next may statically render at build time and the page freezes
 * with whatever the database held during deployment. Everything here is live
 * operational data, and a manager acting on a stale queue is worse than a
 * manager waiting a moment for a fresh one.
 */
export const dynamic = "force-dynamic";

const AXES = Object.keys(dimensionLabels) as BarsDimension[];

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "Aug 29" from an ISO created_at, read in UTC — the same day-label style
 * the results pages use, so the queue card ages honestly with real data. */
function dayLabel(isoDate: string): string {
  const date = new Date(isoDate);
  return Number.isNaN(date.getTime())
    ? isoDate.slice(0, 10)
    : `${MONTH_SHORT[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

/** Avatar initials. The server names the person when it knows them, and the
 * roster (seed) answers when it does not, which is what mock mode relies on.
 * Preferring the server matters once the queue is real: those rows carry
 * database ids, and looking a uuid up in the mock roster produces "?". */
const initialsFor = (staffId: string, staffName?: string): string => {
  const name =
    staffName ?? staffMembers.find((s) => s.id === staffId)?.name;
  if (!name) return "?";
  const fromWords = name
    .split(" ")
    .map((part) => part[0])
    .join("");
  return fromWords || "?";
};

/** Queue rows lead with the person, not the metadata. */
const nameFor = (staffId: string, staffName?: string): string =>
  staffName ??
  staffMembers.find((s) => s.id === staffId)?.name ??
  "Staff member";

/** Aggregate row some backends may add across dimensions (the frozen contract
 * leaves it to the reading list; when absent, take the mean of the rated
 * dimensions so the manager always sees one overall percentage). */
function overallCalibration(rows: CalibrationReading[]): CalibrationSummary | null {
  if (rows.length === 0) return null;
  const aggregate = rows.find(
    (r) => (r.dimension as string) === "overall"
  );
  if (aggregate) {
    return {
      rate: aggregate.agreement_rate,
      sampleSize: aggregate.sample_size,
      dimensionCount: Math.max(rows.length - 1, 0),
      state: aggregate.state,
      advice: aggregate.advice,
    };
  }
  const rated = rows.filter(
    (r): r is CalibrationReading & { agreement_rate: number } =>
      r.agreement_rate !== null
  );
  if (rated.length === 0) return null;
  const mean =
    rated.reduce((sum, r) => sum + r.agreement_rate, 0) / rated.length;
  return {
    rate: mean,
    sampleSize: rows.reduce((sum, r) => sum + r.sample_size, 0),
    dimensionCount: rated.length,
    state: null,
    advice: null,
  };
}

export default async function ManagerOverviewPage() {
  // Everything here is per-person, so the roster and the observations together
  // decide the fan-out.
  const [roster, recommendations, readings, insights, observations] =
    await Promise.all([
      managerApi.listStaff(),
      managerApi.listRecommendations(),
      managerApi.getCalibration(),
      managerApi.getTeamInsights(),
      managerApi.listObservations().catch(() => []),
    ]);

  // One request per person, because a gap is computed per staff member under
  // that viewer's permissions and there is no bulk endpoint that would not
  // quietly bypass row level security.
  //
  // But it only has to ask about people who HAVE a gap, and a transfer gap
  // cannot exist before the manager has observed someone: it is the distance
  // between their practice score and that observation. Asking about the other
  // forty-odd returns nothing and was most of the five seconds this page took
  // to load. Credit to Ziyi for spotting it.
  const observedIds = new Set(observations.map((o) => o.staff_id));
  const gaps = await Promise.all(
    roster.filter((s) => observedIds.has(s.id)).map((s) => managerApi.getGap(s.id))
  );

  const pending = recommendations.filter(
    (r) => r.status === "pending_verify"
  );
  const oldestPending =
    pending.length > 0
      ? pending.reduce((oldest, rec) =>
          rec.created_at < oldest.created_at ? rec : oldest
        )
      : null;
  const calibration = overallCalibration(readings);

  const teamGaps = gaps.filter(
    (g): g is TransferGap => g !== undefined && g.dimensions.length > 0
  );
  const teamPractice: Partial<Record<BarsDimension, number | null>> = {};
  const teamFloor: Partial<Record<BarsDimension, number | null>> = {};
  for (const dim of AXES) {
    const rows = teamGaps.flatMap((g) =>
      g.dimensions.filter((d) => d.dimension === dim)
    );
    if (rows.length === 0) {
      teamPractice[dim] = null;
      teamFloor[dim] = null;
      continue;
    }
    teamPractice[dim] =
      rows.reduce((sum, r) => sum + r.practice_mean, 0) / rows.length;
    teamFloor[dim] =
      rows.reduce((sum, r) => sum + r.floor_mean, 0) / rows.length;
  }
  const emptyDims = AXES.filter((a) => teamPractice[a] == null);

  return (
    <div className="space-y-6">
      <div className="msg-in flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Afternoon, Marta
          </h1>
          <p className="text-sm text-muted-foreground">
            {pending.length} recommendations are waiting on your read. Nothing
            routes anywhere until you verify.
          </p>
        </div>
        <Button nativeButton={false} render={<Link href="/manager/observe" />}>
          <ClipboardCheck className="size-4" />
          Log an observation
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="surface-glow fade-up lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Team transfer-gap radar
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Practice mean vs what you saw on the floor, per dimension. Where
              the dashed floor line dips inside the solid practice line, that
              dimension is the transfer gap.
            </p>
          </CardHeader>
          <CardContent>
            <RadarChart
              axes={AXES}
              series={[
                {
                  id: "practice",
                  label: "Practice mean",
                  values: teamPractice,
                  color: "var(--chart-1)",
                },
                {
                  id: "floor",
                  label: "Floor mean",
                  values: teamFloor,
                  color: "var(--chart-2)",
                  dashed: true,
                },
              ]}
              showValues={false}
            />
            <RadarCaption
              observedStaffCount={teamGaps.length}
              emptyDimensions={emptyDims.map((d) => dimensionShort[d])}
            />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="fade-up [animation-delay:120ms]">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <ListChecks className="size-4 text-primary" />
                Verify queue
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold tabular-nums">
                {pending.length}
              </p>
              <p className="text-xs text-muted-foreground">
                {oldestPending
                  ? `pending · oldest from ${dayLabel(oldestPending.created_at)}`
                  : "pending · nothing waiting"}
              </p>
              <Button
                variant="link"
                className="-mx-2 mt-1 h-auto min-h-9 px-2"
                nativeButton={false}
                render={<Link href="/manager/verify" />}
              >
                Open the queue <ArrowRight className="size-3.5" />
              </Button>
            </CardContent>
          </Card>

          <CalibrationCard summary={calibration} />

          <Card className="fade-up [animation-delay:360ms]">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <TrendingUp className="size-4 text-primary" />
                Team patterns
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold tabular-nums">
                {insights.patterns.length}
              </p>
              <p className="text-xs text-muted-foreground">
                Hidden until at least {insights.k_threshold} staff share a
                pattern.
              </p>
              <Button
                variant="link"
                className="-mx-2 mt-1 h-auto min-h-9 px-2"
                nativeButton={false}
                render={<Link href="/manager/insights" />}
              >
                View insights <ArrowRight className="size-3.5" />
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card className="fade-up [animation-delay:480ms]">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Verify queue</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {pending.map((rec) => (
            <Link
              key={rec.id}
              href={`/manager/verify/${rec.id}`}
              className="flex items-center gap-3 rounded-xl border p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-muted/40 hover:shadow-sm"
            >
              <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-foreground">
                {initialsFor(rec.staff_id, rec.staff_name)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">
                  {nameFor(rec.staff_id, rec.staff_name)}
                </p>
                <p className="truncate text-sm leading-snug text-muted-foreground">
                  {rec.headline}
                </p>
              </div>
              <ArrowRight className="size-4 text-muted-foreground" />
            </Link>
          ))}
        </CardContent>
      </Card>

      <p className="fade-up [animation-delay:600ms] rounded-xl border border-dashed border-primary/25 bg-primary/5 p-4 text-xs leading-relaxed text-muted-foreground">
        <span className="font-semibold text-foreground">How it works:</span>{" "}
        your observation and the staff member's practice scores are two
        independent streams. The AI combines them into a transfer-gap reading,
        drafts a recommendation where every claim cites its source, and holds
        it here until you confirm, correct or reject it. Every verdict trains
        the calibration number shown above, that is the loop the system
        learns from. Simulations only prove what staff can do in practice.
        Cornell's own AI-training research stops there. The floor is where it
        counts.
      </p>
    </div>
  );
}
