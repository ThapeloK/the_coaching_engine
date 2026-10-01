import { ArrowDownRight, ArrowUpRight, EyeOff, ShieldCheck, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { WeeklyBriefCard } from "@/features/manager-console/components/weekly-brief-card";
import { classificationMeta, dimensionShort } from "@/lib/format";
import type { EscalationRoute, TeamPattern } from "@/lib/types";


/** Rendered per request, never prerendered.
 *
 * Without this Next may statically render at build time and the page freezes
 * with whatever the database held during deployment. Everything here is live
 * operational data, and a manager acting on a stale queue is worse than a
 * manager waiting a moment for a fresh one.
 */
export const dynamic = "force-dynamic";

export const metadata = { title: "Team insights · Manager Console" };

const routeLabel: Record<EscalationRoute, string> = {
  manager: "Duty manager",
  ld_hr: "LD/HR",
  operations: "Operations / GM",
};

/**
 * Trend data is not part of the frozen TeamPattern yet — the cohort service
 * may attach it later. When it does, it arrives in the same weekly-gap shape
 * the transfer-gap dimensions use (seed.ts), so derive up/down from the first
 * and last points. Anything unrecognised renders nothing rather than guessing.
 */
interface TrendReading {
  direction: "up" | "down";
  span: string | null;
}

function readTrend(pattern: TeamPattern): TrendReading | null {
  const raw = (pattern as TeamPattern & { trend?: unknown }).trend;
  if (raw === undefined || raw === null) return null;
  if (typeof raw === "string") {
    const direction =
      raw === "rising" || raw === "up" || raw === "worsening"
        ? "up"
        : raw === "falling" || raw === "down" || raw === "improving"
          ? "down"
          : null;
    return direction ? { direction, span: null } : null;
  }
  if (typeof raw !== "object") return null;
  const direction =
    "direction" in raw &&
    (raw.direction === "up" || raw.direction === "down")
      ? raw.direction
      : null;
  if (direction) return { direction, span: null };
  if (Array.isArray(raw) && raw.length >= 2) {
    const points = raw as Array<{ week?: unknown; gap?: unknown }>;
    const firstGap = points[0]?.gap;
    const lastGap = points[points.length - 1]?.gap;
    if (typeof firstGap !== "number" || typeof lastGap !== "number") {
      return null;
    }
    const direction =
      lastGap > firstGap + 0.0001
        ? "up"
        : lastGap < firstGap - 0.0001
          ? "down"
          : null;
    if (!direction) return null;
    const weeks = points
      .map((p) => p.week)
      .filter((w): w is string => typeof w === "string");
    return {
      direction,
      span:
        weeks.length >= 2 ? `${weeks[0]}–${weeks[weeks.length - 1]}` : null,
    };
  }
  return null;
}


/** The situation is the tail of the generated description, after the colon:
 * "10 staff in f and b logged the same situation this period: service delay."
 * Falls back to the whole sentence if that shape ever changes. */
function situationOf(description: string): string {
  const tail = description.split(":").slice(1).join(":").trim();
  const text = (tail || description).replace(/\.$/, "");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default async function InsightsPage() {
  const insights = await managerApi.getTeamInsights();
  // The bars are relative to the biggest pattern, not to the team size:
  // the question a manager asks here is which of these is worst, not what
  // share of the roster it covers.
  const widestPattern = Math.max(
    1,
    ...insights.patterns.map((p) => p.staff_count)
  );

  return (
    <div className="space-y-6">
      <div className="msg-in">
        <h1 className="text-2xl font-semibold tracking-tight">Team insights</h1>
        <p className="text-sm text-muted-foreground">
          Patterns across the whole team, shown only when at least{" "}
          {insights.k_threshold} staff share them, so no individual can be
          singled out. Individual coaching is suppressed when the root cause
          is process or policy.
        </p>
      </div>

      <div className="fade-up [animation-delay:100ms] flex flex-wrap gap-2 text-xs">
        <span className="flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-muted-foreground">
          Window {insights.window.start} → {insights.window.end}
        </span>
        <span className="flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-muted-foreground">
          <ShieldCheck className="size-3.5 text-primary" />
          k-anonymity threshold: {insights.k_threshold}
        </span>
      </div>

      <WeeklyBriefCard patternCount={insights.patterns.length} />

      <div className="space-y-3">
        {[...insights.patterns]
          .sort((a, b) => b.staff_count - a.staff_count)
          .map((pattern, i) => {
          const trend = readTrend(pattern);
          return (
            <Card
              key={pattern.id}
              className="fade-up transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm"
              style={{ animationDelay: `${200 + i * 100}ms` }}
            >
              <CardContent className="space-y-3 p-4 md:p-5">
                {/* Headcount leads. It is what makes a pattern a pattern, what
                    k-anonymity counts, and the only thing that separates these
                    rows at a glance. */}
                <div className="flex items-start gap-4">
                  <div className="w-14 shrink-0 text-right">
                    <p className="text-2xl font-semibold leading-none tabular-nums">
                      {pattern.staff_count}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      staff
                    </p>
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <h2 className="text-base font-semibold leading-snug">
                        {situationOf(pattern.description)}
                      </h2>
                      <span className="text-xs text-muted-foreground">
                        {dimensionShort[pattern.dimension]} ·{" "}
                        {classificationMeta[pattern.classification].label}
                      </span>
                    </div>

                    {/* Relative scale, so ten against five is visible without
                        reading either number. */}
                    <div
                      aria-hidden
                      className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className="h-full rounded-full bg-primary/60"
                        style={{
                          width: `${Math.round(
                            (pattern.staff_count / widestPattern) * 100
                          )}%`,
                        }}
                      />
                    </div>

                    <p className="mt-2 text-sm leading-snug text-muted-foreground">
                      {pattern.suggested_action}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 pl-0 text-xs sm:pl-[4.5rem]">
                  {trend && (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 font-semibold ${
                        trend.direction === "up"
                          ? "bg-[oklch(0.66_0.09_30)]/12 text-[oklch(0.45_0.08_30)]"
                          : "bg-[oklch(0.76_0.07_74)]/15 text-[oklch(0.45_0.07_72)]"
                      }`}
                    >
                      {trend.direction === "up" ? (
                        <ArrowUpRight className="size-3.5" />
                      ) : (
                        <ArrowDownRight className="size-3.5" />
                      )}
                      {trend.direction === "up"
                        ? "Trending up"
                        : "Trending down"}
                      {trend.span ? ` · ${trend.span}` : ""}
                    </span>
                  )}
                  {/* The routing and the reason are one thought, so they get
                      one line rather than two rows of chrome under two rows of
                      content. */}
                  <span className="text-muted-foreground">
                    {classificationMeta[pattern.classification].hint}
                  </span>
                  <Badge className="ml-auto shrink-0 bg-primary text-primary-foreground">
                    → {routeLabel[pattern.route]}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          );
        })}

        {insights.suppressed.map((s) => (
          <div
            key={s.reason}
            className="flex items-center gap-3 rounded-xl border border-dashed p-4 text-sm text-muted-foreground"
          >
            <EyeOff className="size-4 shrink-0" />
            {s.count} pattern{s.count > 1 ? "s" : ""} hidden, group smaller
            than {insights.k_threshold} staff, so they can&apos;t be shown
            without identifying someone.
          </div>
        ))}
      </div>

      <p className="flex items-start gap-2 rounded-xl bg-muted/40 p-4 text-xs leading-relaxed text-muted-foreground">
        <Users className="mt-0.5 size-4 shrink-0" />
        No individual staff surveillance: insights aggregate at team level,
        every flag explains why it was raised, and staff can see every record
        a manager can see about them.
      </p>
    </div>
  );
}
