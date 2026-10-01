import type { BarsDimension, Observation } from "@/lib/types";
import { rosterIdOf } from "./team-staff";

/**
 * Authoritative floor observations from the team's generated dataset
 * (`observations.json`, seed 20260913, 22 rows, all observed by Marta on
 * staff-001..staff-013). Rows import 1:1: ids, dates and texts verbatim.
 * `staff_name`/`manager_name` are dropped (the roster names them) and the
 * ratings object — which the pipeline emits with explicit nulls — becomes
 * the API's ratings array with only the rated dimensions.
 */

export interface TeamObservationRow {
  id: string;
  staff_id: string;
  observed_at: string;
  context: string;
  what_happened: string;
  ratings: Partial<Record<BarsDimension, number | null>>;
}

export const TEAM_OBSERVATION_ROWS: TeamObservationRow[] = [
  { id: "obs-001", staff_id: "staff-001", observed_at: "2026-08-29", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 3, communication: null, composure: 3, service_recovery: 2, anticipation: null } },
  { id: "obs-002", staff_id: "staff-002", observed_at: "2026-08-30", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 3, communication: null, composure: 4, service_recovery: 4, anticipation: null } },
  { id: "obs-003", staff_id: "staff-002", observed_at: "2026-08-31", context: "Busy check-in queue, four deep", what_happened: "Kept the queue informed and stayed composed. Handled it well.", ratings: { empathy: null, communication: 4, composure: 3, service_recovery: null, anticipation: 3 } },
  { id: "obs-004", staff_id: "staff-002", observed_at: "2026-08-29", context: "Checkout billing query", what_happened: "Explained clearly but did not offer any goodwill gesture, went straight to me.", ratings: { empathy: null, communication: 3, composure: null, service_recovery: 4, anticipation: null } },
  { id: "obs-005", staff_id: "staff-003", observed_at: "2026-09-04", context: "Checkout billing query", what_happened: "Explained clearly but did not offer any goodwill gesture, went straight to me.", ratings: { empathy: null, communication: 4, composure: null, service_recovery: 4, anticipation: null } },
  { id: "obs-006", staff_id: "staff-004", observed_at: "2026-09-06", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 4, communication: null, composure: 3, service_recovery: 3, anticipation: null } },
  { id: "obs-007", staff_id: "staff-005", observed_at: "2026-09-10", context: "Busy check-in queue, four deep", what_happened: "Kept the queue informed and stayed composed. Handled it well.", ratings: { empathy: null, communication: 4, composure: 3, service_recovery: null, anticipation: 4 } },
  { id: "obs-008", staff_id: "staff-005", observed_at: "2026-09-05", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 2, communication: null, composure: 4, service_recovery: 3, anticipation: null } },
  { id: "obs-009", staff_id: "staff-006", observed_at: "2026-09-04", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 3, communication: null, composure: 2, service_recovery: 3, anticipation: null } },
  { id: "obs-010", staff_id: "staff-006", observed_at: "2026-09-06", context: "Busy check-in queue, four deep", what_happened: "Kept the queue informed and stayed composed. Handled it well.", ratings: { empathy: null, communication: 4, composure: 3, service_recovery: null, anticipation: 3 } },
  { id: "obs-011", staff_id: "staff-007", observed_at: "2026-08-29", context: "Checkout billing query", what_happened: "Explained clearly but did not offer any goodwill gesture, went straight to me.", ratings: { empathy: null, communication: 4, composure: null, service_recovery: 4, anticipation: null } },
  { id: "obs-012", staff_id: "staff-007", observed_at: "2026-09-07", context: "Busy check-in queue, four deep", what_happened: "Kept the queue informed and stayed composed. Handled it well.", ratings: { empathy: null, communication: 3, composure: 2, service_recovery: null, anticipation: 3 } },
  { id: "obs-013", staff_id: "staff-008", observed_at: "2026-09-07", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 3, communication: null, composure: 3, service_recovery: 4, anticipation: null } },
  { id: "obs-014", staff_id: "staff-009", observed_at: "2026-09-10", context: "Guest complaint at front desk, room not ready at 3pm", what_happened: "Froze, then escalated to me without attempting recovery herself.", ratings: { empathy: 4, communication: null, composure: 2, service_recovery: 4, anticipation: null } },
  { id: "obs-015", staff_id: "staff-010", observed_at: "2026-09-04", context: "Late mains on a table of six", what_happened: "Apologised, acknowledged the specific delay, comped coffees. Textbook A.L.O.U.D.", ratings: { empathy: 4, communication: null, composure: 4, service_recovery: 4, anticipation: null } },
  { id: "obs-016", staff_id: "staff-010", observed_at: "2026-08-28", context: "Guest unhappy with wine recommendation", what_happened: "Listened without interrupting and offered an alternative. Good.", ratings: { empathy: 4, communication: 4, composure: null, service_recovery: null, anticipation: null } },
  { id: "obs-017", staff_id: "staff-011", observed_at: "2026-09-06", context: "Guest unhappy with wine recommendation", what_happened: "Listened without interrupting and offered an alternative. Good.", ratings: { empathy: 4, communication: 3, composure: null, service_recovery: null, anticipation: null } },
  { id: "obs-018", staff_id: "staff-011", observed_at: "2026-08-31", context: "Guest unhappy with wine recommendation", what_happened: "Listened without interrupting and offered an alternative. Good.", ratings: { empathy: 4, communication: 4, composure: null, service_recovery: null, anticipation: null } },
  { id: "obs-019", staff_id: "staff-012", observed_at: "2026-08-31", context: "Late mains on a table of six", what_happened: "Apologised, acknowledged the specific delay, comped coffees. Textbook A.L.O.U.D.", ratings: { empathy: 4, communication: null, composure: 4, service_recovery: 4, anticipation: null } },
  { id: "obs-020", staff_id: "staff-012", observed_at: "2026-08-28", context: "Guest unhappy with wine recommendation", what_happened: "Listened without interrupting and offered an alternative. Good.", ratings: { empathy: 4, communication: 3, composure: null, service_recovery: null, anticipation: null } },
  { id: "obs-021", staff_id: "staff-012", observed_at: "2026-09-10", context: "Late mains on a table of six", what_happened: "Apologised, acknowledged the specific delay, comped coffees. Textbook A.L.O.U.D.", ratings: { empathy: 4, communication: null, composure: 3, service_recovery: 3, anticipation: null } },
  { id: "obs-022", staff_id: "staff-013", observed_at: "2026-09-10", context: "Guest unhappy with wine recommendation", what_happened: "Listened without interrupting and offered an alternative. Good.", ratings: { empathy: 4, communication: 3, composure: null, service_recovery: null, anticipation: null } },
];

/** Deterministic dimension order for ratings arrays (matches ALL_DIMENSIONS in
 * db.ts, so store snapshots and API payloads are stable). */
const RATING_ORDER: BarsDimension[] = [
  "service_recovery",
  "empathy",
  "anticipation",
  "communication",
  "composure",
];

/**
 * The 22 observations the mock store seeds, roster-keyed (staff-001 maps to
 * Diego's legacy id "9f2c-diego"). `observed_at` stays exactly as generated;
 * `created_at` is a deterministic noon stamp — the pipeline JSON has no
 * created_at of its own.
 */
export const seedObservations: Observation[] = TEAM_OBSERVATION_ROWS.map(
  (row) => ({
    id: row.id,
    staff_id: rosterIdOf(row.staff_id),
    observed_at: row.observed_at,
    created_at: `${row.observed_at}T12:00:00Z`,
    context: row.context,
    what_happened: row.what_happened,
    ratings: RATING_ORDER.flatMap((dimension) => {
      const level = row.ratings[dimension];
      return level === null || level === undefined
        ? []
        : [{ dimension, level }];
    }),
  })
);
