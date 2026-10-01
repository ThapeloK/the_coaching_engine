"use client";

import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { dimensionShort } from "@/lib/format";
import type { StaffScoreRow } from "@/lib/types";

/**
 * HLD §6.1/§10: the last-three-scores panel on the gap page, manager view.
 * Only the floor stream — the manager's own observations — is read. The
 * practice side is a privacy note: practice scores are never shown to a
 * manager, raw or aggregated, at any time. The system compares the streams
 * silently and only surfaces the coaching insight. (The frozen 409 gate on
 * `source=practice` still stands for other callers; the manager console no
 * longer asks for practice at all.)
 */

type FloorState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; rows: StaffScoreRow[] };

const RECENT_LIMIT = 3;

const AMBER_TEXT = "text-[oklch(0.45_0.07_72)]";
const ROSE_TEXT = "text-[oklch(0.45_0.08_30)]";
const ROSE_PILL =
  "bg-[oklch(0.66_0.09_30)]/12 text-[oklch(0.45_0.08_30)] border-[oklch(0.66_0.09_30)]/30";

export function LastScoresPanel({ staffId }: { staffId: string }) {
  const [floor, setFloor] = useState<FloorState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setFloor({ kind: "loading" });
    managerApi
      .getScores(staffId, "floor")
      .then((res) => {
        if (cancelled) return;
        const rows = [...res.scores].sort((a, b) =>
          b.recorded_at.localeCompare(a.recorded_at)
        );
        setFloor({ kind: "ready", rows });
      })
      .catch(() => {
        if (!cancelled) setFloor({ kind: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [staffId]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Practice side: a privacy note, not a stream. Practice scores stay
          with the staff member, the manager's read is the insight only. */}
      <div className="rounded-xl border bg-card p-4">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className={`size-2 rounded-full bg-current ${AMBER_TEXT}`}
          />
          <p className="text-sm font-semibold">Practice history</p>
        </div>
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-dashed p-3">
          <Lock className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          <p className="text-xs leading-relaxed text-muted-foreground">
            Practice history stays private, the system compares it silently
            and only surfaces the coaching insight.
          </p>
        </div>
      </div>

      <StreamCard state={floor} />
    </div>
  );
}

function StreamCard({ state }: { state: FloorState }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className={`size-2 rounded-full bg-current ${ROSE_TEXT}`}
        />
        <p className="text-sm font-semibold">Floor history</p>
        {state.kind === "ready" && state.rows.length > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">
            {state.rows.length > RECENT_LIMIT
              ? `last ${RECENT_LIMIT} of ${state.rows.length}`
              : `last ${state.rows.length}`}{" "}
            · newest first
          </span>
        )}
      </div>

      {state.kind === "loading" && (
        <p className="mt-3 text-xs text-muted-foreground">
          Reading your observations…
        </p>
      )}

      {state.kind === "error" && (
        <p className="mt-3 rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
          Could not read the floor record right now, refresh to retry.
        </p>
      )}

      {state.kind === "ready" && state.rows.length === 0 && (
        <p className="mt-3 rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
          No floor scores yet, they fill in once an observation is logged.
        </p>
      )}

      {state.kind === "ready" && state.rows.length > 0 && (
        <ul className="mt-3 space-y-2">
          {state.rows.slice(0, RECENT_LIMIT).map((row) => (
            <li
              key={row.id}
              className="flex items-center justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {dimensionShort[row.dimension]}
                </p>
                <p className="text-xs tabular-nums text-muted-foreground">
                  {row.recorded_at.slice(0, 10)}
                </p>
              </div>
              <span
                className={`rounded-md border px-2 py-0.5 text-sm font-bold tabular-nums ${
                  row.level === null
                    ? "border-transparent bg-muted text-muted-foreground"
                    : ROSE_PILL
                }`}
              >
                {row.level ?? "–"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
