import type {
  BarsDimension,
  EvidenceSpan,
  PracticeAttempt,
  ScoreResult,
} from "@/lib/types";
import { rosterIdOf } from "./team-staff";

/**
 * Authoritative practice attempts from the team's generated dataset
 * (`attempts.json`, seed 20260913): 45 completed runs across staff-001..013.
 * Every field imports 1:1 — id, staff, scenario title, completion date,
 * scores, turn count.
 *
 * The dataset stores scores and turn counts but no transcripts, so each
 * attempt's evidence span is synthesized from its own record: a factual
 * descriptor of the run (scenario, date, turns, level). No quote is invented.
 *
 * Scenario mapping: "Room not ready at check-in" / "Noise complaint at 23:00"
 * / "Late main course, wrong order" are the s1/s2/s3 starter scenarios. The
 * other two titles exist only in attempts.json — the dataset ships no
 * scenario registry for them (seed.sql has none) — so they get structural
 * ids that never appear in GET /scenarios: those runs are history, not
 * replayable scenarios.
 */

export interface TeamAttemptRow {
  id: string;
  staff_id: string;
  scenario_title: string;
  completed_at: string;
  /** Only the dimensions the pipeline scored (nulls are absent, not zero). */
  scores: Partial<Record<BarsDimension, number>>;
  turns: number;
}

/** Registered starter scenarios versus structural ids for unregistered titles. */
export const SCENARIO_ID_BY_TITLE: Record<string, string> = {
  "Room not ready at check-in": "s1-starter",
  "Noise complaint at 23:00": "s2-starter",
  "Late main course, wrong order": "s3-starter",
  "Guest disputes a charge at checkout": "charge-dispute-starter",
  "Guest asks about allergens": "allergen-starter",
};

/** One line per dataset row (id, staff, title, date, scores, turns). */
const R: TeamAttemptRow[] = [
  { id: "att-001", staff_id: "staff-001", scenario_title: "Noise complaint at 23:00", completed_at: "2026-09-07", scores: { empathy: 4, composure: 4 }, turns: 8 },
  { id: "att-002", staff_id: "staff-001", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-18", scores: { empathy: 4, composure: 4 }, turns: 6 },
  { id: "att-003", staff_id: "staff-001", scenario_title: "Room not ready at check-in", completed_at: "2026-08-29", scores: { empathy: 4, composure: 4, service_recovery: 4 }, turns: 6 },
  { id: "att-004", staff_id: "staff-001", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-16", scores: { empathy: 4, composure: 4 }, turns: 9 },
  { id: "att-005", staff_id: "staff-001", scenario_title: "Room not ready at check-in", completed_at: "2026-08-30", scores: { empathy: 4, composure: 4, service_recovery: 4 }, turns: 7 },
  { id: "att-006", staff_id: "staff-002", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-09-08", scores: { communication: 3, service_recovery: 4 }, turns: 9 },
  { id: "att-007", staff_id: "staff-002", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-08-24", scores: { communication: 4, service_recovery: 4 }, turns: 10 },
  { id: "att-008", staff_id: "staff-002", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-15", scores: { empathy: 3, composure: 3 }, turns: 10 },
  { id: "att-009", staff_id: "staff-003", scenario_title: "Room not ready at check-in", completed_at: "2026-09-05", scores: { empathy: 4, composure: 4, service_recovery: 4 }, turns: 9 },
  { id: "att-010", staff_id: "staff-003", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-17", scores: { empathy: 4, composure: 3 }, turns: 10 },
  { id: "att-011", staff_id: "staff-003", scenario_title: "Room not ready at check-in", completed_at: "2026-08-31", scores: { empathy: 5, composure: 4, service_recovery: 3 }, turns: 6 },
  { id: "att-012", staff_id: "staff-004", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-08-14", scores: { communication: 4, service_recovery: 3 }, turns: 9 },
  { id: "att-013", staff_id: "staff-004", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-09-04", scores: { communication: 3, service_recovery: 3 }, turns: 7 },
  { id: "att-014", staff_id: "staff-004", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-23", scores: { empathy: 4, composure: 4 }, turns: 10 },
  { id: "att-015", staff_id: "staff-005", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-16", scores: { empathy: 3, composure: 2 }, turns: 8 },
  { id: "att-016", staff_id: "staff-005", scenario_title: "Noise complaint at 23:00", completed_at: "2026-08-29", scores: { empathy: 3, composure: 3 }, turns: 10 },
  { id: "att-017", staff_id: "staff-005", scenario_title: "Room not ready at check-in", completed_at: "2026-09-07", scores: { empathy: 3, composure: 5, service_recovery: 3 }, turns: 7 },
  { id: "att-018", staff_id: "staff-006", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-09-03", scores: { communication: 4, service_recovery: 5 }, turns: 6 },
  { id: "att-019", staff_id: "staff-006", scenario_title: "Room not ready at check-in", completed_at: "2026-09-05", scores: { empathy: 3, composure: 3, service_recovery: 4 }, turns: 6 },
  { id: "att-020", staff_id: "staff-006", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-08-14", scores: { communication: 3, service_recovery: 3 }, turns: 6 },
  { id: "att-021", staff_id: "staff-006", scenario_title: "Noise complaint at 23:00", completed_at: "2026-09-02", scores: { empathy: 3, composure: 3 }, turns: 10 },
  { id: "att-022", staff_id: "staff-007", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-09-09", scores: { communication: 3, service_recovery: 4 }, turns: 10 },
  { id: "att-023", staff_id: "staff-007", scenario_title: "Room not ready at check-in", completed_at: "2026-08-28", scores: { empathy: 3, composure: 4, service_recovery: 3 }, turns: 10 },
  { id: "att-024", staff_id: "staff-007", scenario_title: "Room not ready at check-in", completed_at: "2026-08-14", scores: { empathy: 4, composure: 3, service_recovery: 3 }, turns: 10 },
  { id: "att-025", staff_id: "staff-007", scenario_title: "Noise complaint at 23:00", completed_at: "2026-09-08", scores: { empathy: 5, composure: 4 }, turns: 7 },
  { id: "att-026", staff_id: "staff-008", scenario_title: "Room not ready at check-in", completed_at: "2026-08-24", scores: { empathy: 3, composure: 4, service_recovery: 4 }, turns: 7 },
  { id: "att-027", staff_id: "staff-008", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-08-31", scores: { communication: 4, service_recovery: 4 }, turns: 7 },
  { id: "att-028", staff_id: "staff-008", scenario_title: "Noise complaint at 23:00", completed_at: "2026-09-04", scores: { empathy: 3, composure: 3 }, turns: 10 },
  { id: "att-029", staff_id: "staff-008", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-08-17", scores: { communication: 4, service_recovery: 3 }, turns: 6 },
  { id: "att-030", staff_id: "staff-009", scenario_title: "Guest disputes a charge at checkout", completed_at: "2026-08-19", scores: { communication: 3, service_recovery: 4 }, turns: 10 },
  { id: "att-031", staff_id: "staff-009", scenario_title: "Room not ready at check-in", completed_at: "2026-08-29", scores: { empathy: 4, composure: 4, service_recovery: 4 }, turns: 9 },
  { id: "att-032", staff_id: "staff-009", scenario_title: "Noise complaint at 23:00", completed_at: "2026-09-04", scores: { empathy: 4, composure: 3 }, turns: 7 },
  { id: "att-033", staff_id: "staff-010", scenario_title: "Late main course, wrong order", completed_at: "2026-08-20", scores: { empathy: 4, service_recovery: 5 }, turns: 8 },
  { id: "att-034", staff_id: "staff-010", scenario_title: "Guest asks about allergens", completed_at: "2026-09-07", scores: { communication: 5, anticipation: 5 }, turns: 8 },
  { id: "att-035", staff_id: "staff-010", scenario_title: "Late main course, wrong order", completed_at: "2026-08-14", scores: { empathy: 4, service_recovery: 4 }, turns: 9 },
  { id: "att-036", staff_id: "staff-010", scenario_title: "Guest asks about allergens", completed_at: "2026-08-22", scores: { communication: 4, anticipation: 5 }, turns: 9 },
  { id: "att-037", staff_id: "staff-011", scenario_title: "Late main course, wrong order", completed_at: "2026-08-26", scores: { empathy: 3, service_recovery: 4 }, turns: 6 },
  { id: "att-038", staff_id: "staff-011", scenario_title: "Late main course, wrong order", completed_at: "2026-09-10", scores: { empathy: 3, service_recovery: 4 }, turns: 6 },
  { id: "att-039", staff_id: "staff-011", scenario_title: "Guest asks about allergens", completed_at: "2026-09-04", scores: { communication: 4, anticipation: 4 }, turns: 7 },
  { id: "att-040", staff_id: "staff-012", scenario_title: "Late main course, wrong order", completed_at: "2026-08-17", scores: { empathy: 4, service_recovery: 4 }, turns: 9 },
  { id: "att-041", staff_id: "staff-012", scenario_title: "Late main course, wrong order", completed_at: "2026-09-06", scores: { empathy: 3, service_recovery: 3 }, turns: 8 },
  { id: "att-042", staff_id: "staff-012", scenario_title: "Guest asks about allergens", completed_at: "2026-08-20", scores: { communication: 5, anticipation: 4 }, turns: 10 },
  { id: "att-043", staff_id: "staff-013", scenario_title: "Late main course, wrong order", completed_at: "2026-08-14", scores: { empathy: 3, service_recovery: 3 }, turns: 7 },
  { id: "att-044", staff_id: "staff-013", scenario_title: "Guest asks about allergens", completed_at: "2026-08-19", scores: { communication: 4, anticipation: 4 }, turns: 10 },
  { id: "att-045", staff_id: "staff-013", scenario_title: "Late main course, wrong order", completed_at: "2026-09-06", scores: { empathy: 3, service_recovery: 5 }, turns: 9 },
];

/** Display labels matching the app's existing copy for these five dimensions. */
const DIMENSION_LABEL: Record<BarsDimension, string> = {
  service_recovery: "Service recovery",
  empathy: "Empathy",
  anticipation: "Anticipation",
  communication: "Communication",
  composure: "Composure",
};

/** Evidence spans carry no quotes — only factual descriptors of the run. */
function evidenceFor(row: TeamAttemptRow): EvidenceSpan[] {
  return (
    Object.entries(row.scores) as Array<[BarsDimension, number]>
  ).map(([dimension, level]) => ({
    dimension,
    quote: `Level ${level} on "${row.scenario_title}", ${row.turns} turns, completed ${row.completed_at}.`,
    turn_index: 0,
    explains:
      "The generated dataset records scores and turn counts, not transcripts, so this span is the scoring row itself, nothing is invented.",
  }));
}

function feedbackFor(row: TeamAttemptRow): string {
  const parts = (
    Object.entries(row.scores) as Array<[BarsDimension, number]>
  )
    .map(([dimension, level]) => `${DIMENSION_LABEL[dimension]} ${level}`)
    .join(", ");
  return `Completed ${row.completed_at} on "${row.scenario_title}" (${row.turns} turns): ${parts}. The dataset carries scores and turn counts only, so there is no transcript to quote for a finer reading.`;
}

function resultFor(row: TeamAttemptRow): ScoreResult {
  return {
    attempt_id: row.id,
    scenario_id: SCENARIO_ID_BY_TITLE[row.scenario_title] ?? row.scenario_title,
    completed_at: row.completed_at,
    scores: (
      Object.entries(row.scores) as Array<[BarsDimension, number]>
    ).map(([dimension, level]) => ({ dimension, level })),
    evidence: evidenceFor(row),
    overall_feedback: feedbackFor(row),
  };
}

/**
 * The mock store's 45 real completed attempts, roster-keyed (staff-001 →
 * "9f2c-diego") and ordered by completion date. The frozen API type carries
 * no staff_id, so attribution rides on the stored record type db.ts uses.
 */
export type SeedAttempt = PracticeAttempt & { staff_id: string };

export const seedAttempts: SeedAttempt[] = [...R]
  .sort((a, b) => a.completed_at.localeCompare(b.completed_at))
  .map((row) => ({
    id: row.id,
    scenario_id: SCENARIO_ID_BY_TITLE[row.scenario_title] ?? row.scenario_title,
    status: "completed",
    turns: [],
    result: resultFor(row),
    staff_id: rosterIdOf(row.staff_id),
  }));
