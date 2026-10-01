import { NextResponse } from "next/server";
import { isKnownStaffId, mockDb } from "@/lib/mock/db";
import { z } from "zod";
import type {
  ScoreSource,
  ScoresResponse,
  StaffScoreRow,
} from "@/lib/types";

/**
 * GET /staff/{id}/scores?source=practice|floor
 *
 * Contract (openapi.yaml): reading a staff member's practice history is a
 * SEQUENCING rule, not a permission check. Until the manager has logged their
 * own floor observation of this person, `source=practice` answers 409 — the
 * manager's judgement is captured first, or the transfer gap measures an
 * echo instead of a transfer.
 *
 * Practice rows come from the stored attempts attributed to this staff
 * member (the 45 real seeded runs carry their own staff_id; runtime runs
 * belong to the pinned staff-PWA actor). Floor rows come from the stored
 * observations of this staff member. Every roster member in the seeded
 * dataset has at least one real observation; staff-014/015 (Marta, Fiona)
 * are known to the system but unobserved, so the 409 gate is exercised by
 * them — for a new hire the same rule applies with a fresh observation.
 */

/** Query contract: `?source=practice|floor` — validated with zod, never by hand. */
const ScoresQuerySchema = z.object({
  source: z.enum(["practice", "floor"]),
});

function problem(status: number, title: string, detail: string) {
  return NextResponse.json(
    { type: "about:blank", title, status, detail },
    { status, headers: { "Content-Type": "application/problem+json" } }
  );
}

/** Practice rows: one per scored dimension of this staff member's attempts. */
async function rowsFromAttempts(staffId: string): Promise<StaffScoreRow[]> {
  const attempts = await mockDb.listAttempts();
  return attempts
    .filter((attempt) => attempt.staff_id === staffId)
    .flatMap((attempt) => {
      if (attempt.status !== "completed" || !attempt.result) {
        return [];
      }
      const evidenceByDimension = new Map(
        attempt.result.evidence.map((e) => [e.dimension, e.quote])
      );
      return attempt.result.scores
        .filter(({ level }) => level !== null)
        .map(({ dimension, level }) => ({
          id: `${attempt.id}:${dimension}`,
          source: "practice" as const,
          dimension,
          level,
          recorded_at: attempt.result!.completed_at,
          evidence_span: evidenceByDimension.get(dimension) ?? null,
        }));
    });
}

/** Floor rows: one per dimension the manager rated in an observation. */
async function rowsFromObservations(staffId: string): Promise<StaffScoreRow[]> {
  const observations = await mockDb.listObservations();
  return observations
    .filter((o) => o.staff_id === staffId)
    .flatMap((o) =>
      o.ratings
        .filter(({ level }) => level !== null)
        .map(({ dimension, level }) => ({
          id: `${o.id}:${dimension}`,
          source: "floor" as const,
          dimension,
          level,
          recorded_at: o.observed_at,
          evidence_span: o.what_happened,
        }))
    );
}

const byNewestFirst = (a: StaffScoreRow, b: StaffScoreRow) =>
  b.recorded_at.localeCompare(a.recorded_at);

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const query = ScoresQuerySchema.safeParse({
    source: new URL(request.url).searchParams.get("source"),
  });
  if (!query.success) {
    return problem(
      400,
      "Invalid source",
      "`source` is required and must be one of: practice, floor."
    );
  }
  const source: ScoreSource = query.data.source;

  try {
    if (!isKnownStaffId(id)) {
      return problem(404, "Not found", "No scores data for this staff member");
    }

    const observations = (await mockDb.listObservations()).filter(
      (o) => o.staff_id === id
    );

    // Sequencing gate: the manager's own observation must exist before the
    // system reveals practice history (contract: 409, not 403).
    if (source === "practice" && observations.length === 0) {
      return problem(
        409,
        "Observation required first",
        "Log a floor observation for this staff member before reading their practice history: your own judgement is captured first, or the transfer gap measures an echo, not a transfer."
      );
    }

    const rows =
      source === "practice"
        ? await rowsFromAttempts(id)
        : await rowsFromObservations(id);
    rows.sort(byNewestFirst);

    const payload: ScoresResponse = {
      staff_id: id,
      source,
      scores: rows,
    };
    return NextResponse.json(payload);
  } catch (error) {
    console.error("Failed to read staff scores:", error);
    return problem(500, "Internal error", "Could not read scores right now");
  }
}
