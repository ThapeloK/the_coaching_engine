import Link from "next/link";
import { GapQuadrant } from "@/features/manager-console/components/gap-quadrant";
import { LastScoresPanel } from "@/features/manager-console/components/last-scores-panel";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { RadarChart } from "@/components/ui/radar-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { staffMembers } from "@/lib/mock/seed";
import { dimensionLabels } from "@/lib/format";
import type { BarsDimension } from "@/lib/types";


/** Rendered per request, never prerendered.
 *
 * Without this Next may statically render at build time and the page freezes
 * with whatever the database held during deployment. Everything here is live
 * operational data, and a manager acting on a stale queue is worse than a
 * manager waiting a moment for a fresh one.
 */
export const dynamic = "force-dynamic";

export const metadata = { title: "Transfer gap · Manager Console" };

const AXES = Object.keys(dimensionLabels) as BarsDimension[];

export default async function GapPage(
  props: PageProps<"/manager/gap">
) {
  const search = await props.searchParams;
  const staffId = typeof search.staff === "string" ? search.staff : "9f2c-diego";
  const gap = await managerApi.getGap(staffId);

  // Who needs looking at, not who exists. One request: a recommendation only
  // exists where a gap was found, so pending counts rank the row without the
  // per-person fan-out that makes the overview slow.
  const [roster, openReads] = await Promise.all([
    managerApi.listStaff().catch(() => []),
    managerApi.listRecommendations().catch(() => []),
  ]);
  const openByStaff = new Map<string, number>();
  for (const r of openReads) {
    if (r.status !== "pending_verify") continue;
    openByStaff.set(r.staff_id, (openByStaff.get(r.staff_id) ?? 0) + 1);
  }
  const switcher = (roster.length ? roster : staffMembers)
    .map((m) => ({ ...m, open: openByStaff.get(m.id) ?? 0 }))
    .sort((a, b) => b.open - a.open || a.name.localeCompare(b.name));
  const staff = staffMembers.find((s) => s.id === staffId);

  const practiceValues: Partial<Record<BarsDimension, number | null>> = {};
  const floorValues: Partial<Record<BarsDimension, number | null>> = {};
  if (gap) {
    for (const d of gap.dimensions) {
      practiceValues[d.dimension] = d.practice_mean;
      floorValues[d.dimension] = d.floor_mean;
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Transfer gap · {staff?.name ?? staffId}
        </h1>
        <p className="text-sm text-muted-foreground">
          Practice performance vs what you actually saw on the floor. Two
          streams, one reading, computed only once your observation is in.
        </p>
      </div>

      {/* Team switcher, ordered by who has reads waiting. The badge is the
          count, so the row answers "who needs me" before it is scrolled. */}
      <nav aria-label="Team members" className="flex gap-2 overflow-x-auto pb-1">
        {switcher.map((member) => {
          const active = member.id === staffId;
          return (
            <Link
              key={member.id}
              href={`/manager/gap?staff=${member.id}`}
              aria-current={active ? "page" : undefined}
              className={`inline-flex min-h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-3.5 text-sm font-medium transition-all duration-150 ${
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-card text-muted-foreground hover:-translate-y-px hover:border-primary/40 hover:text-foreground hover:shadow-sm"
              }`}
            >
              {member.name.split(" ")[0]}
              {member.open > 0 && (
                <span
                  title={`${member.open} waiting on your read`}
                  className={`inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold tabular-nums ${
                    active
                      ? "bg-primary-foreground/25"
                      : "bg-[oklch(0.76_0.07_74)]/25 text-[oklch(0.42_0.07_72)]"
                  }`}
                >
                  {member.open}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {gap ? (
        <>
          {/* The conclusion card and per-dimension badge rows carry the
              reading; the radar chart stays below as supporting evidence. */}
          <GapQuadrant gap={gap} staffName={staff?.name ?? "staff member"} />
          <LastScoresPanel key={staffId} staffId={staffId} />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                Practice vs floor radar for{" "}
                {(staff?.name ?? "staff member").split(" ")[0]}
              </CardTitle>
              <p className="text-xs text-muted-foreground">
                Supporting chart: the scored dimensions at a glance. Solid =
                practice (simulation). Dashed = floor (observed). Where the
                dashed line falls inside the solid one, the floor is trailing
                practice. That is the transfer gap.
              </p>
            </CardHeader>
            <CardContent className="mx-auto w-full max-w-sm">
              <RadarChart
                axes={AXES}
                series={[
                  {
                    id: "practice",
                    label: "Practice mean",
                    values: practiceValues,
                    color: "var(--chart-1)",
                  },
                  {
                    id: "floor",
                    label: "Floor mean",
                    values: floorValues,
                    color: "var(--chart-2)",
                    dashed: true,
                  },
                ]}
                caption="Where the dashed line falls inside the solid one the floor is trailing practice. Unscored axes sit at the centre"
                showValues={false}
              />
            </CardContent>
          </Card>
        </>
      ) : (
        <p className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
          No gap data yet for {staff ? staff.name.split(" ")[0] : "this staff member"}
          . Log a floor observation first, and the transfer gap appears once both
          streams have scores.
        </p>
      )}
    </div>
  );
}
