import type { BarsDimension, Quadrant } from "@/lib/types";

/**
 * Authoritative transfer-gap rows from the team's generated dataset
 * (`transfer_gaps.json`, seed 20260913): 65 rows = 13 staff × 5 dimensions,
 * keyed by pipeline staff id (staff-001..staff-013). Numbers import 1:1 —
 * the dataset computed plain means and the quadrant/rules pipeline produced
 * these quadrants, so the mock serves them verbatim instead of recomputing
 * (a recompute would need the real 28-day weighted pipeline and would still
 * round-trip less faithfully than the snapshot).
 *
 * Diego's row set is exactly the narrative gap the app already told
 * (service_recovery 4.0/2.0/gap 2.0 blocked; empathy + composure 4.0/3.0/
 * gap 1.0 blocked; communication + anticipation insufficient_evidence) —
 * the story numbers and the dataset were built from the same source.
 */

export type GapRowStatus = "ok" | "insufficient_evidence";

export interface TeamGapRow {
  staff_id: string;
  dimension: BarsDimension;
  practice_mean: number | null;
  floor_mean: number | null;
  gap: number | null;
  quadrant: Quadrant | null;
  practice_n: number;
  floor_n: number;
  status: GapRowStatus;
}

/** Compact row builder — keeps the 65 dataset rows to one line each. */
function row(
  staff_id: string,
  dimension: BarsDimension,
  practice_mean: number | null,
  floor_mean: number | null,
  gap: number | null,
  quadrant: Quadrant | null,
  practice_n: number,
  floor_n: number,
  status: GapRowStatus
): TeamGapRow {
  return {
    staff_id,
    dimension,
    practice_mean,
    floor_mean,
    gap,
    quadrant,
    practice_n,
    floor_n,
    status,
  };
}

export const TEAM_GAP_ROWS: TeamGapRow[] = [
  // staff-001 Diego — the narrative transfer gap, exactly as generated.
  row("staff-001", "empathy", 4.0, 3.0, 1.0, "blocked", 5, 1, "ok"),
  row("staff-001", "communication", null, null, null, null, 0, 0, "insufficient_evidence"),
  row("staff-001", "composure", 4.0, 3.0, 1.0, "blocked", 5, 1, "ok"),
  row("staff-001", "service_recovery", 4.0, 2.0, 2.0, "blocked", 2, 1, "ok"),
  row("staff-001", "anticipation", null, null, null, null, 0, 0, "insufficient_evidence"),
  // staff-002 Niamh
  row("staff-002", "empathy", 3.0, 3.0, 0.0, "skill_gap", 1, 1, "ok"),
  row("staff-002", "communication", 3.5, 3.5, 0.0, "competent", 2, 2, "ok"),
  row("staff-002", "composure", 3.0, 3.5, -0.5, "recalibrate", 1, 2, "ok"),
  row("staff-002", "service_recovery", 4.0, 4.0, 0.0, "competent", 2, 2, "ok"),
  row("staff-002", "anticipation", null, 3.0, null, null, 0, 1, "insufficient_evidence"),
  // staff-003 Tomasz
  row("staff-003", "empathy", 4.33, null, null, null, 3, 0, "insufficient_evidence"),
  row("staff-003", "communication", null, 4.0, null, null, 0, 1, "insufficient_evidence"),
  row("staff-003", "composure", 3.67, null, null, null, 3, 0, "insufficient_evidence"),
  row("staff-003", "service_recovery", 3.5, 4.0, -0.5, "competent", 2, 1, "ok"),
  row("staff-003", "anticipation", null, null, null, null, 0, 0, "insufficient_evidence"),
  // staff-004 Rachel
  row("staff-004", "empathy", 4.0, 4.0, 0.0, "competent", 1, 1, "ok"),
  row("staff-004", "communication", 3.5, null, null, null, 1, 0, "insufficient_evidence"),
  row("staff-004", "composure", 4.0, 3.0, 1.0, "blocked", 1, 1, "ok"),
  row("staff-004", "service_recovery", 3.0, 3.0, 0.0, "skill_gap", 2, 1, "ok"),
  row("staff-004", "anticipation", null, null, null, null, 0, 0, "insufficient_evidence"),
  // staff-005 Kwame
  row("staff-005", "empathy", 3.0, 2.0, 1.0, "skill_gap", 3, 1, "ok"),
  row("staff-005", "communication", null, 4.0, null, null, 0, 1, "insufficient_evidence"),
  row("staff-005", "composure", 3.33, 3.5, -0.17, "recalibrate", 3, 2, "ok"),
  row("staff-005", "service_recovery", 3.0, 3.0, 0.0, "skill_gap", 1, 1, "ok"),
  row("staff-005", "anticipation", null, 4.0, null, null, 0, 1, "insufficient_evidence"),
  // staff-006 Lucia
  row("staff-006", "empathy", 3.0, 3.0, 0.0, "skill_gap", 2, 1, "ok"),
  row("staff-006", "communication", 3.5, 4.0, -0.5, "competent", 2, 1, "ok"),
  row("staff-006", "composure", 3.0, 2.5, 0.5, "skill_gap", 2, 2, "ok"),
  row("staff-006", "service_recovery", 4.0, 3.0, 1.0, "blocked", 3, 1, "ok"),
  row("staff-006", "anticipation", null, 3.0, null, null, 0, 1, "insufficient_evidence"),
  // staff-007 Sean
  row("staff-007", "empathy", 4.0, null, null, null, 3, 0, "insufficient_evidence"),
  row("staff-007", "communication", 3.0, 3.5, -0.5, "recalibrate", 1, 2, "ok"),
  row("staff-007", "composure", 3.67, 2.0, 1.67, "blocked", 3, 1, "ok"),
  row("staff-007", "service_recovery", 3.33, 4.0, -0.67, "recalibrate", 3, 1, "ok"),
  row("staff-007", "anticipation", null, 3.0, null, null, 0, 1, "insufficient_evidence"),
  // staff-008 Priya
  row("staff-008", "empathy", 3.0, 3.0, 0.0, "skill_gap", 2, 1, "ok"),
  row("staff-008", "communication", 4.0, null, null, null, 2, 0, "insufficient_evidence"),
  row("staff-008", "composure", 3.5, 3.0, 0.5, "blocked", 2, 1, "ok"),
  row("staff-008", "service_recovery", 3.67, 4.0, -0.33, "competent", 3, 1, "ok"),
  row("staff-008", "anticipation", null, null, null, null, 0, 0, "insufficient_evidence"),
  // staff-009 Andrei
  row("staff-009", "empathy", 4.0, 4.0, 0.0, "competent", 2, 1, "ok"),
  row("staff-009", "communication", 3.0, null, null, null, 1, 0, "insufficient_evidence"),
  row("staff-009", "composure", 3.5, 2.0, 1.5, "blocked", 2, 1, "ok"),
  row("staff-009", "service_recovery", 4.0, 4.0, 0.0, "competent", 2, 1, "ok"),
  row("staff-009", "anticipation", null, null, null, null, 0, 0, "insufficient_evidence"),
  // staff-010 Aoife
  row("staff-010", "empathy", 4.0, 4.0, 0.0, "competent", 2, 2, "ok"),
  row("staff-010", "communication", 4.5, 4.0, 0.5, "competent", 2, 1, "ok"),
  row("staff-010", "composure", null, 4.0, null, null, 0, 1, "insufficient_evidence"),
  row("staff-010", "service_recovery", 4.5, 4.0, 0.5, "competent", 2, 1, "ok"),
  row("staff-010", "anticipation", 5.0, null, null, null, 2, 0, "insufficient_evidence"),
  // staff-011 Marek
  row("staff-011", "empathy", 3.0, 4.0, -1.0, "recalibrate", 2, 2, "ok"),
  row("staff-011", "communication", 4.0, 3.5, 0.5, "competent", 1, 2, "ok"),
  row("staff-011", "composure", null, null, null, null, 0, 0, "insufficient_evidence"),
  row("staff-011", "service_recovery", 4.0, null, null, null, 2, 0, "insufficient_evidence"),
  row("staff-011", "anticipation", 4.0, null, null, null, 1, 0, "insufficient_evidence"),
  // staff-012 Chloe
  row("staff-012", "empathy", 3.5, 4.0, -0.5, "competent", 2, 3, "ok"),
  row("staff-012", "communication", 5.0, 3.0, 2.0, "blocked", 1, 1, "ok"),
  row("staff-012", "composure", null, 3.5, null, null, 0, 2, "insufficient_evidence"),
  row("staff-012", "service_recovery", 3.5, 3.5, 0.0, "competent", 2, 2, "ok"),
  row("staff-012", "anticipation", 4.0, null, null, null, 1, 0, "insufficient_evidence"),
  // staff-013 Bogdan
  row("staff-013", "empathy", 3.0, 4.0, -1.0, "recalibrate", 2, 1, "ok"),
  row("staff-013", "communication", 4.0, 3.0, 1.0, "blocked", 1, 1, "ok"),
  row("staff-013", "composure", null, null, null, null, 0, 0, "insufficient_evidence"),
  row("staff-013", "service_recovery", 4.0, null, null, null, 3, 0, "insufficient_evidence"),
  row("staff-013", "anticipation", 4.0, null, null, null, 1, 0, "insufficient_evidence"),
];

/** Deterministic dimension order used whenever rows are grouped into the API's
 * per-staff TransferGap (mirrors ALL_DIMENSIONS in db.ts). */
export const GAP_DIMENSION_ORDER: BarsDimension[] = [
  "service_recovery",
  "empathy",
  "anticipation",
  "communication",
  "composure",
];

/** All rows for one pipeline staff id (identity when no legacy mapping). */
export function gapRowsForTeamStaff(teamStaffId: string): TeamGapRow[] {
  return TEAM_GAP_ROWS.filter((r) => r.staff_id === teamStaffId);
}

/** The staff whose transfer gaps carry a finding (blocked or skill_gap) on a
 * dimension — the deficit cohort routing.py and the team insights count. */
export function findingStaffIds(
  rows: TeamGapRow[],
  dimension: BarsDimension
): string[] {
  return rows
    .filter(
      (r) =>
        r.dimension === dimension &&
        r.status === "ok" &&
        (r.quadrant === "blocked" || r.quadrant === "skill_gap")
    )
    .map((r) => r.staff_id);
}
