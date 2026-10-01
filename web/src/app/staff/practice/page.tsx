import Link from "next/link";
import { Play, Sparkles, Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { staffApi } from "@/features/staff-pwa/api/staffApi";
import { dimensionShort } from "@/lib/format";


/** Rendered per request, never prerendered.
 *
 * Without this Next may statically render at build time and the page freezes
 * with whatever the database held during deployment. Everything here is live
 * operational data, and a manager acting on a stale queue is worse than a
 * manager waiting a moment for a fresh one.
 */
export const dynamic = "force-dynamic";

export default async function PracticeListPage() {
  const scenarios = await staffApi.listScenarios();
  const personal = scenarios.filter((s) => s.kind === "personal");
  const starters = scenarios.filter((s) => s.kind === "starter");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Practice</h1>
        <p className="text-xs text-muted-foreground">
          3 minutes each. When you finish, every label comes back with the
          exact words that earned it, and it stays yours.
        </p>
      </div>

      {personal.map((scenario) => (
        <Link
          key={scenario.id}
          href={`/staff/practice/${scenario.id}`}
          className="group block rounded-2xl border bg-card p-4"
        >
          <div className="flex items-center gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[oklch(0.66_0.055_152)]/15">
              <Sparkles className="size-4 text-[oklch(0.38_0.055_152)]" />
            </div>
            <p className="min-w-0 flex-1 text-xs font-semibold uppercase tracking-wide text-primary">
              Built from your shift
            </p>
            <Badge className="shrink-0 bg-[oklch(0.66_0.055_152)]/15 text-[oklch(0.38_0.055_152)]">
              {scenario.duration_minutes} min
            </Badge>
          </div>
          <p className="mt-3 text-base font-semibold">{scenario.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {scenario.description}
          </p>
          <div className="mt-3 flex items-center gap-2 text-xs font-medium text-primary">
            <Play className="size-3.5" />
            Practise it now while it&apos;s fresh
          </div>
        </Link>
      ))}

      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Starter scenarios
        </p>
        <div className="mt-2 space-y-2">
          {starters.map((scenario) => (
            <Link
              key={scenario.id}
              href={`/staff/practice/${scenario.id}`}
              className="flex items-center gap-3 rounded-2xl border bg-card p-4"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent">
                <Star className="size-4 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{scenario.title}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {scenario.dimensions.map((d) => dimensionShort[d]).join(" · ")}
                </p>
              </div>
              <span className="text-xs text-muted-foreground">
                {scenario.duration_minutes} min
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
