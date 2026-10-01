import * as seedModule from "@/lib/mock/seed";
import { rosterIdOf, teamIdOf, TEAM_STAFF_ROWS } from "./team-staff";
import type { TeamInsights } from "@/lib/types";
import type {
  BarsDimension,
  Calibration,
  CalibrationDimension,
  Debrief,
  Escalation,
  EvidenceSpan,
  GuestTurn,
  Observation,
  ObservationInput,
  ObservationResponse,
  PracticeAttempt,
  Recommendation,
  Scenario,
  ScoreResult,
  StandardReference,
  TransferGap,
  TurnResponse,
  VerifyInput,
  VerifyResponse,
} from "@/lib/types";
import type { TeamGapRow } from "./team-gaps";

/**
 * In-memory mock store. Every function mirrors a frozen LLD-B endpoint.
 * Business rules are ported 1:1 from the team's real agent services so the
 * mock behaves like the real backend:
 *   - calibration: services/agent/coaching_engine/calibration.py
 *     (Wilson interval, z = 1.96, provisional < 10, reliable lower >= 0.75,
 *     unreliable upper < 0.65)
 *   - transfer gap: services/agent/coaching_engine/transfer_gap.py
 *     (STRONG 3.5, MIN_ATTEMPTS/MIN_OBSERVATIONS 1, 28-day half-life weights)
 *   - escalation routing: services/agent/coaching_engine/routing.py
 *     (RC-* rules, first match wins, route/severity vocabulary)
 * Swap to the real API by setting USE_REAL_API — see src/lib/api/client.ts.
 */

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ── Seed imports ─────────────────────────────────────────────────────────────
// Roster ids come from seed.ts's `staffMembers` (the 13 staff of the dataset;
// Diego is staff-001 under the legacy id "9f2c-diego"). Dataset rows arrive
// through seed.ts's re-exports of the team-*.ts files: the 22 real
// observations and 45 real practice attempts (already roster-keyed, attempts
// carrying their own staff_id), plus the transfer_gap rows the gap/insights
// surfaces serve verbatim. No dynamic shape-guessing is needed anymore.

const seedStaffMembers = seedModule.staffMembers as {
  id: string;
  name: string;
}[];
const knownStaffIds = new Set(seedStaffMembers.map((s) => s.id));

/** Staff the API recognises: the 13 observable roster ids plus the two
 * non-roster pipeline staff (staff-014 Marta, staff-015 Fiona) under their
 * team ids — lets endpoints distinguish "known but unobserved" (409) from
 * "unknown" (404). Team ids of roster staff (e.g. staff-001) stay unknown:
 * the app never issues them. */
const allStaffIds = new Set(
  TEAM_STAFF_ROWS.flatMap((row) =>
    row.role === "staff" ? [rosterIdOf(row.id)] : [row.id]
  )
);

export function isKnownStaffId(id: string): boolean {
  return allStaffIds.has(id);
}

const ALL_DIMENSIONS: BarsDimension[] = [
  "service_recovery",
  "empathy",
  "anticipation",
  "communication",
  "composure",
];

/** An attempt as the mock stores it. The frozen API type carries no staff_id,
 * so attribution lives on the stored record: the /staff/{id}/scores route
 * (and any caller) can enumerate real practice history via `listAttempts()`
 * instead of guessing from the seed module. */
export type AttemptRecord = PracticeAttempt & { staff_id: string | null };

const seedAttempts = seedModule.seedAttempts;
const seedObservations = seedModule.seedObservations;

/**
 * The staff-PWA's single actor, pinned by seed.ts ("9f2c-diego"). Runtime
 * practice attempts created by `startAttempt` — and the seeded in-progress
 * personal replay — are attributed to this id, so the manager's practice
 * reads for that staff member grow honestly at demo time.
 */
const staffPwaActor = seedModule.staffPwaActorStaffId;

// ── Guest dialogue (per-scenario scripts from seed, never mixed) ────────────

const GUEST_MOODS = new Set(["neutral", "frustrated", "escalating", "calming"]);

interface GuestScriptLine {
  content: string;
  mood: GuestTurn["mood"];
}

/** The script seed.ts registers for one scenario: the opening guest message
 * plus one reply per staff turn. Read dynamically so a colleague editing
 * seed.ts in parallel needs no db.ts change. Never falls back to another
 * scenario's script — callers use their own neutral fallback instead. */
function guestScriptFor(scenarioId: string): {
  opener: GuestScriptLine;
  replies: GuestScriptLine[];
} | null {
  const scripts = (seedModule as unknown as {
    guestScripts?: Record<string, unknown>;
  }).guestScripts;
  const script = scripts?.[scenarioId];
  if (!script || typeof script !== "object") return null;
  const asRecord = script as Record<string, unknown>;
  const line = (raw: unknown): GuestScriptLine | null => {
    if (!raw || typeof raw !== "object") return null;
    const o = raw as Record<string, unknown>;
    if (typeof o.content !== "string" || o.content.trim() === "") return null;
    const mood =
      typeof o.mood === "string" && GUEST_MOODS.has(o.mood)
        ? o.mood
        : "neutral";
    return { content: o.content, mood: mood as GuestTurn["mood"] };
  };
  const opener = line(asRecord.opener);
  const replies = Array.isArray(asRecord.replies)
    ? asRecord.replies.map(line).filter((l): l is GuestScriptLine => l !== null)
    : [];
  return opener && replies.length > 0 ? { opener, replies } : null;
}

/** Honest fallback when a scenario has no script of its own (a future
 * addition): a neutral, scenario-agnostic line — never another scenario's
 * script — so the flow stays usable without pretending to know the guest. */
const UNSCRIPTED_OPENERS: GuestScriptLine[] = [
  { content: "I could do with some help, please.", mood: "neutral" },
];
const UNSCRIPTED_REPLIES: GuestScriptLine[] = [
  { content: "Go on.", mood: "neutral" },
  { content: "I see.", mood: "neutral" },
  { content: "Thank you, and what happens next?", mood: "neutral" },
];

// ── Immutable snapshots (callers never reach into the store) ────────────────

function cloneAttempt(attempt: AttemptRecord): AttemptRecord {
  return {
    ...attempt,
    turns: attempt.turns.map((t) => ({ ...t, guest: { ...t.guest } })),
    result: attempt.result
      ? {
          ...attempt.result,
          scores: attempt.result.scores.map((s) => ({ ...s })),
          evidence: attempt.result.evidence.map((e) => ({ ...e })),
        }
      : null,
  };
}

function cloneObservation(observation: Observation): Observation {
  return {
    ...observation,
    ratings: observation.ratings.map((r) => ({ ...r })),
  };
}

// ── Calibration (calibration.py) ─────────────────────────────────────────────

type CalibrationState =
  | "unmeasured"
  | "provisional"
  | "reliable"
  | "uncertain"
  | "unreliable";

const Z_95 = 1.96;
const PROVISIONAL_BELOW_N = 10;
const RELIABLE_LOWER_BOUND = 0.75;
const UNRELIABLE_UPPER_BOUND = 0.65;

interface LedgerEntry {
  agreements: number;
  n: number;
}

interface CalibrationReading {
  dimension: BarsDimension;
  agreement_rate: number | null;
  lower: number | null;
  upper: number | null;
  sample_size: number;
  state: CalibrationState;
  advice: string;
}

/** Wilson score interval — the real formula from calibration.py. */
function wilsonInterval(agreements: number, n: number): {
  rate: number;
  lower: number;
  upper: number;
} {
  if (n <= 0) throw new Error("calibration n must be positive");
  if (agreements < 0 || agreements > n) {
    throw new Error("agreements must be between 0 and n");
  }
  const p = agreements / n;
  const denom = 1 + (Z_95 * Z_95) / n;
  const centre = (p + (Z_95 * Z_95) / (2 * n)) / denom;
  const half =
    (Z_95 *
      Math.sqrt((p * (1 - p)) / n + (Z_95 * Z_95) / (4 * n * n))) /
    denom;
  return {
    rate: p,
    lower: Math.max(0, centre - half),
    upper: Math.min(1, centre + half),
  };
}

/** State machine from calibration.py `calibrate`. */
function calibrateState(n: number, lower: number, upper: number): CalibrationState {
  if (n === 0) return "unmeasured";
  if (n < PROVISIONAL_BELOW_N) return "provisional";
  if (lower >= RELIABLE_LOWER_BOUND) return "reliable";
  if (upper < UNRELIABLE_UPPER_BOUND) return "unreliable";
  return "uncertain";
}

/** Manager-facing sentence, mirroring calibration.py `Calibration.display`. */
function calibrationAdvice(
  rate: number | null,
  n: number,
  state: CalibrationState
): string {
  if (state === "unmeasured") {
    return "Not yet measured on this dimension.";
  }
  const pct = Math.round((rate ?? 0) * 100);
  if (state === "provisional") {
    return `Agrees with your managers ${pct}% of the time so far, on only ${n} checks.`;
  }
  if (state === "unreliable") {
    return `Agrees with your managers ${pct}% of the time on this dimension. Treat with caution. We route these to a human first.`;
  }
  if (state === "uncertain") {
    return `Agrees with your managers ${pct}% of the time (${n} checks). Still settling.`;
  }
  return `Agrees with your managers ${pct}% of the time (${n} checks).`;
}

function computeReading(
  dimension: BarsDimension,
  entry: LedgerEntry
): CalibrationReading {
  if (entry.n === 0) {
    return {
      dimension,
      agreement_rate: null,
      lower: null,
      upper: null,
      sample_size: 0,
      state: "unmeasured",
      advice: calibrationAdvice(null, 0, "unmeasured"),
    };
  }
  const { rate, lower, upper } = wilsonInterval(entry.agreements, entry.n);
  const state = calibrateState(entry.n, lower, upper);
  const rateRounded = Math.round(rate * 1000) / 1000;
  return {
    dimension,
    agreement_rate: rateRounded,
    lower: Math.round(lower * 1000) / 1000,
    upper: Math.round(upper * 1000) / 1000,
    sample_size: entry.n,
    state,
    advice: calibrationAdvice(rateRounded, entry.n, state),
  };
}

const round3 = (v: number) => Math.round(v * 1000) / 1000;

// ── Transfer gap (transfer_gap.py) ───────────────────────────────────────────

type Quadrant = "competent" | "blocked" | "recalibrate" | "skill_gap";
type ScoreSource = "practice" | "floor";

interface ScoredEvidence {
  dimension: BarsDimension;
  level: number; // 1..5
  scored_at: string; // ISO
  source: ScoreSource;
}

const STRONG = 3.5; // at or above -> competent on this dimension
const MIN_OBSERVATIONS = 1;
const MIN_ATTEMPTS = 1;
const HALF_LIFE_DAYS = 28;

/** Exponential recency weight: 2^(-age_days / 28), as in transfer_gap.py. */
function weight(ageDays: number): number {
  return 2 ** (-ageDays / HALF_LIFE_DAYS);
}

/** As-of date is the latest score date in the pool so no score is ever
 * "in the future" relative to the reference point. */
function poolAsOf(scores: ScoredEvidence[]): Date {
  let latest = Date.now();
  for (const s of scores) {
    const t = new Date(s.scored_at).getTime();
    if (Number.isFinite(t) && t > latest) latest = t;
  }
  return new Date(latest);
}

function weightedMean(
  scores: ScoredEvidence[],
  asOf: Date
): number | null {
  if (scores.length === 0) return null;
  let totalWeight = 0;
  let weightedSum = 0;
  for (const s of scores) {
    const ageDays = Math.max(0, (asOf.getTime() - new Date(s.scored_at).getTime()) / 86_400_000);
    const w = weight(ageDays);
    totalWeight += w;
    weightedSum += w * s.level;
  }
  if (totalWeight === 0) return null;
  return weightedSum / totalWeight;
}

function quadrantFor(
  practiceMean: number | null,
  floorMean: number | null,
  practiceN: number,
  floorN: number
): Quadrant | null {
  if (practiceN < MIN_ATTEMPTS || floorN < MIN_OBSERVATIONS) return null;
  if (practiceMean === null || floorMean === null) return null;
  const practiceStrong = practiceMean >= STRONG;
  const floorStrong = floorMean >= STRONG;
  if (practiceStrong && floorStrong) return "competent";
  if (practiceStrong && !floorStrong) return "blocked";
  if (!practiceStrong && floorStrong) return "recalibrate";
  return "skill_gap";
}

interface GapReading {
  dimension: BarsDimension;
  practiceMean: number | null;
  floorMean: number | null;
  practiceN: number;
  floorN: number;
  quadrant: Quadrant | null;
}

function practicePoolScores(staffId: string | null): ScoredEvidence[] {
  const out: ScoredEvidence[] = [];
  for (const attempt of [...store.attempts.values()]) {
    if (staffId !== null && attempt.staff_id !== staffId) continue;
    if (attempt.status !== "completed" || !attempt.result) continue;
    for (const s of attempt.result.scores) {
      if (s.level !== null && s.level >= 1 && s.level <= 5) {
        out.push({
          dimension: s.dimension,
          level: s.level,
          scored_at: attempt.result.completed_at,
          source: "practice",
        });
      }
    }
  }
  return out;
}

function computeGapFor(staffId: string): GapReading[] {
  const floorScores: ScoredEvidence[] = store.observations
    .filter((o) => o.staff_id === staffId)
    .flatMap((o) =>
      o.ratings.flatMap((r) =>
        r.level !== null && r.level >= 1 && r.level <= 5
          ? [
              {
                dimension: r.dimension as BarsDimension,
                level: r.level,
                scored_at: o.observed_at ?? o.created_at,
                source: "floor" as ScoreSource,
              },
            ]
          : []
      )
    );
  // Practice is attributed per stored record (see AttemptRecord). Staff with
  // no attributed attempts honestly have an empty practice stream.
  const practiceScores = practicePoolScores(staffId);

  const perDimension = new Map<BarsDimension, { practice: ScoredEvidence[]; floor: ScoredEvidence[] }>();
  for (const dim of ALL_DIMENSIONS) {
    perDimension.set(dim, { practice: [], floor: [] });
  }
  for (const s of practiceScores) {
    perDimension.get(s.dimension)?.practice.push(s);
  }
  for (const s of floorScores) {
    perDimension.get(s.dimension)?.floor.push(s);
  }

  const asOf = poolAsOf([...practiceScores, ...floorScores]);
  const readings: GapReading[] = [];
  for (const dim of ALL_DIMENSIONS) {
    const { practice, floor } = perDimension.get(dim) ?? { practice: [], floor: [] };
    const practiceMean = weightedMean(practice, asOf);
    const floorMean = weightedMean(floor, asOf);
    readings.push({
      dimension: dim,
      practiceMean:
        practiceMean === null ? null : round3(practiceMean),
      floorMean: floorMean === null ? null : round3(floorMean),
      practiceN: practice.length,
      floorN: floor.length,
      quadrant: quadrantFor(practiceMean, floorMean, practice.length, floor.length),
    });
  }
  return readings;
}

// ── Team-dataset transfer gaps (rows served verbatim from team-gaps) ────────
// GET /staff/{id}/gap answers with the pipeline's own rows from
// transfer_gaps.json (means, n's, quadrants — the frozen truth) instead of a
// mock recompute. Only the weekly trend series is derived here, from the
// seeded practice/floor streams, so the gap page can show movement. For
// Diego the series reproduces the story's flat read exactly: no floor data
// since 29 Aug, so the gap holds W35→W37.

const round2 = (v: number) => Math.round(v * 100) / 100;

/** ISO-8601 week label ("2026-W35") for any parseable date string. */
function isoWeekLabel(value: string): string {
  const d = new Date(value);
  const year = d.getUTCFullYear();
  const jan1 = new Date(Date.UTC(year, 0, 1));
  const dayOrdinal = Math.floor(
    (d.getTime() - jan1.getTime()) / 86_400_000
  );
  // Week of the containing Thursday (ISO 8601); dayOrdinal is 0-based.
  const thursdayOrdinal = dayOrdinal - ((d.getUTCDay() + 6) % 7) + 3;
  const week = 1 + Math.floor(thursdayOrdinal / 7);
  return `${year}-W${String(week).padStart(2, "0")}`;
}

/** The label one week after `label` (all dates here sit inside one year). */
function nextIsoWeekLabel(label: string): string {
  const m = /^(\d{4})-W(\d{2})$/.exec(label);
  if (!m) return label;
  const jan1 = new Date(Date.UTC(Number(m[1]), 0, 1));
  const mondayOffset = (jan1.getUTCDay() + 6) % 7;
  const nextWeekThursday = new Date(
    jan1.getTime() +
      ((Number(m[2]) - 1) * 7 + (3 - mondayOffset) + 7) * 86_400_000
  );
  return isoWeekLabel(nextWeekThursday.toISOString());
}

interface ScoredPoint {
  level: number;
  scoredAt: string;
  source: "practice" | "floor";
}

/** Every scored reading on one dimension for one roster staff member. */
function scoreStreamFor(
  staffRosterId: string,
  dimension: BarsDimension
): ScoredPoint[] {
  const points: ScoredPoint[] = [];
  for (const attempt of store.attempts.values()) {
    if (
      attempt.staff_id !== staffRosterId ||
      attempt.status !== "completed" ||
      !attempt.result
    ) {
      continue;
    }
    for (const s of attempt.result.scores) {
      if (s.dimension === dimension && s.level !== null) {
        points.push({
          level: s.level,
          scoredAt: attempt.result.completed_at,
          source: "practice",
        });
      }
    }
  }
  for (const observation of store.observations) {
    if (observation.staff_id !== staffRosterId) continue;
    for (const r of observation.ratings) {
      if (r.dimension === dimension && r.level !== null) {
        points.push({
          level: r.level,
          scoredAt: observation.observed_at ?? observation.created_at,
          source: "floor",
        });
      }
    }
  }
  return points;
}

/** Weekly practice-minus-floor series: starts at the first week holding both
 * streams, carries the cumulative gap forward through empty weeks, and ends
 * at the staff member's latest scored week. Empty when either stream is
 * missing or the pool is a single point. */
function weeklyTrendFor(
  staffRosterId: string,
  dimension: BarsDimension
): Array<{ week: string; gap: number }> {
  const points = scoreStreamFor(staffRosterId, dimension);
  const hasPractice = points.some((p) => p.source === "practice");
  const hasFloor = points.some((p) => p.source === "floor");
  if (!hasPractice || !hasFloor || points.length < 2) return [];

  const weekOf = (p: ScoredPoint) => isoWeekLabel(p.scoredAt);
  const weeks = [...new Set(points.map(weekOf))].sort();
  const start = weeks.find(
    (w) =>
      points.some((p) => p.source === "practice" && weekOf(p) === w) &&
      points.some((p) => p.source === "floor" && weekOf(p) === w)
  );
  if (!start) return [];
  const end = weeks[weeks.length - 1];

  const meanUpTo = (
    week: string,
    source: ScoredPoint["source"]
  ): number | null => {
    const pool = points.filter((p) => p.source === source && weekOf(p) <= week);
    if (pool.length === 0) return null;
    return pool.reduce((sum, p) => sum + p.level, 0) / pool.length;
  };

  const trend: Array<{ week: string; gap: number }> = [];
  for (let week: string = start; ; week = nextIsoWeekLabel(week)) {
    const practice = meanUpTo(week, "practice");
    const floor = meanUpTo(week, "floor");
    if (practice !== null && floor !== null) {
      trend.push({ week, gap: round2(practice - floor) });
    }
    if (week >= end) break;
  }
  return trend;
}

/** One qualitative sentence per quadrant — the reading a manager acts on is
 * the coaching insight, never the raw numbers behind it. */
function readingFor(row: TeamGapRow): string {
  if (row.quadrant === "blocked") {
    return "Performs it in practice and loses it live, that points at authority or pressure, not skill.";
  }
  if (row.quadrant === "skill_gap") {
    return "Both streams are still building, targeted practice is the right next step.";
  }
  if (row.quadrant === "recalibrate") {
    return "The floor runs ahead of practice, check the rubric and the scenario, not the person.";
  }
  return "Practice and the floor align, the skill is transferring cleanly.";
}

/** The full TransferGap for one roster staff member: dataset rows in
 * ALL_DIMENSIONS order, live trend series, and a computed_at that lands on
 * the staff member's latest scored date (never in the future of their data). */
function buildTransferGap(
  staffRosterId: string
): TransferGap | undefined {
  const rows = seedModule.gapRowsForTeamStaff(teamIdOf(staffRosterId));
  if (rows.length === 0) return undefined;
  const byDimension = new Map(rows.map((r) => [r.dimension, r]));

  const scoredDates: string[] = [];
  for (const observation of store.observations) {
    if (observation.staff_id === staffRosterId) {
      scoredDates.push(observation.observed_at ?? observation.created_at);
    }
  }
  for (const attempt of store.attempts.values()) {
    if (attempt.staff_id === staffRosterId && attempt.result) {
      scoredDates.push(attempt.result.completed_at);
    }
  }
  const computedAt = scoredDates.length
    ? `${[...scoredDates].sort()[scoredDates.length - 1].slice(0, 10)}T12:00:00Z`
    : new Date().toISOString();

  const dimensions: TransferGap["dimensions"] = [];
  const insufficient: TransferGap["insufficient_evidence"] = [];
  for (const dimension of ALL_DIMENSIONS) {
    const row = byDimension.get(dimension);
    if (!row) continue;
    if (
      row.status !== "ok" ||
      row.practice_mean === null ||
      row.floor_mean === null ||
      row.quadrant === null
    ) {
      insufficient.push(dimension);
      continue;
    }
    dimensions.push({
      dimension,
      practice_mean: row.practice_mean,
      practice_n: row.practice_n,
      floor_mean: row.floor_mean,
      floor_n: row.floor_n,
      gap: row.gap ?? round2(row.practice_mean - row.floor_mean),
      quadrant: row.quadrant,
      reading: readingFor(row),
      trend: weeklyTrendFor(staffRosterId, dimension),
    });
  }
  return {
    staff_id: staffRosterId,
    computed_at: computedAt,
    dimensions,
    insufficient_evidence: insufficient,
  };
}

// ── Escalation routing (routing.py) ──────────────────────────────────────────

type Route = "manager" | "ld_hr" | "operations";

interface RoutingContext {
  classification: Recommendation["classification"];
  cohort_size: number;
  floor_mean: number | null;
  floor_n: number;
  floor_trend_slope: number | null;
  days_since_activity: number;
}

const RC_COPY: Record<string, string> = {
  "RC-PROCESS-COHORT":
    "{n} staff hit the same wall this week. This is one process problem, not {n} people needing coaching. Individual coaching is suppressed.",
  "RC-POLICY-COHORT":
    "{n} staff were unclear on what they are permitted to offer. That is a policy gap, not a behavioural one. Suggested action: set and communicate a discretionary limit.",
  "RC-SEVERE":
    "Sustained low floor scores across multiple observations. Routed to L&D for support, not for disciplinary action.",
  "RC-BEHAV-DECLINE":
    "Floor performance has been declining over the last three observations. Worth a conversation before it becomes a pattern.",
  "RC-POLICY-SINGLE":
    "This looks like authority ambiguity rather than a skill gap. Worth confirming what this person believes they are allowed to do.",
  "RC-BEHAV-DEFAULT":
    "An individual coaching conversation is the right next step.",
};

interface RoutingDecision {
  rule_id: string;
  route: Route;
  severity: number; // 1 low, 2 medium, 3 high
  summary: string;
}

/** First match wins; order mirrors routing.py RULES. Returns null when the
 * finding stays at default coaching level (route manager, severity 1) — those
 * are recorded but not surfaced as an escalation. */
function routeFinding(ctx: RoutingContext): RoutingDecision | null {
  const decisions: Array<{
    rule_id: string;
    fires: boolean;
    route: Route;
    severity: number;
  }> = [
    {
      rule_id: "RC-PROCESS-COHORT",
      fires: ctx.classification === "process" && ctx.cohort_size >= 5,
      route: "operations",
      severity: 2,
    },
    {
      rule_id: "RC-POLICY-COHORT",
      fires: ctx.classification === "policy" && ctx.cohort_size >= 3,
      route: "operations",
      severity: 2,
    },
    {
      rule_id: "RC-SEVERE",
      fires:
        ctx.floor_mean !== null && ctx.floor_mean <= 1.5 && ctx.floor_n >= 3,
      route: "ld_hr",
      severity: 3,
    },
    {
      // RC-DISENGAGE needs platform-activity tracking the mock does not have,
      // so it can never honestly fire here.
      rule_id: "RC-BEHAV-DECLINE",
      fires:
        ctx.floor_trend_slope !== null &&
        ctx.floor_trend_slope < -0.5 &&
        ctx.floor_n >= 3,
      route: "manager",
      severity: 2,
    },
    {
      rule_id: "RC-POLICY-SINGLE",
      fires: ctx.classification === "policy",
      route: "manager",
      severity: 1,
    },
    {
      rule_id: "RC-BEHAV-DEFAULT",
      fires: ctx.classification === "behavioural",
      route: "manager",
      severity: 1,
    },
  ];

  for (const d of decisions) {
    if (!d.fires) continue;
    if (d.route === "manager" && d.severity === 1) return null;
    return {
      rule_id: d.rule_id,
      route: d.route,
      severity: d.severity,
      summary: (RC_COPY[d.rule_id] ?? "").replaceAll("{n}", String(ctx.cohort_size)),
    };
  }
  return null;
}

/** Cohort proxy: distinct staff with a real deficit finding (blocked or
 * skill_gap dataset row) on the dimension — routing.py's k-anonymised
 * cohort, counted from transfer_gaps.json rather than guessed. */
function cohortFor(dimension: BarsDimension): number {
  return seedModule.findingStaffIds(seedModule.TEAM_GAP_ROWS, dimension)
    .length;
}

/** Simple OLS slope over time-ordered floor levels (≥ 3 points). */
function floorTrendSlope(staffId: string, dimension: BarsDimension): number | null {
  const levels = store.observations
    .filter((o) => o.staff_id === staffId)
    .flatMap((o) =>
      o.ratings
        .filter((r) => r.dimension === dimension && r.level !== null)
        .map((r) => ({ t: o.observed_at, level: r.level as number }))
    )
    .sort((a, b) => a.t.localeCompare(b.t))
    .map((r) => r.level);
  if (levels.length < 3) return null;
  const xs = levels.map((_, i) => i);
  const meanX = xs.reduce((a, b) => a + b, 0) / xs.length;
  const meanY = levels.reduce((a, b) => a + b, 0) / levels.length;
  let num = 0;
  let den = 0;
  for (let i = 0; i < levels.length; i++) {
    num += (i - meanX) * (levels[i] - meanY);
    den += (i - meanX) ** 2;
  }
  if (den === 0) return null;
  return round3(num / den);
}

// ── Debrief SOP index (grounded in the real corpus + seed standards) ─────────

/** F&B complaints cite the A.L.O.U.D. sequence itself (corpus sop-fnb-complaint,
 * chunks 001–005). A missing meal lands on step 1: the apology before any
 * remedy. */
const ALOUD_STANDARD: StandardReference = {
  chunk_id: "chunk-001",
  document: "Complaint Handling (A.L.O.U.D.)",
  section_path: "Complaint Handling > A.L.O.U.D. > Step 1: Apologies",
  step_number: 1,
  excerpt: "A - Apologies. Apologise sincerely before commenting further.",
  why_shown:
    "You described an order or service problem at a table. The A.L.O.U.D. sequence opens with the apology before any remedy, that is the step to check.",
};

/** Generic room-event fallback (Service Promise) when the seed carries no
 * room standard of its own. */
const FRONT_DESK_STANDARD: StandardReference = {
  chunk_id: "chunk-017",
  document: "The Service Promise",
  section_path: "Service Promise > Principle 3",
  step_number: 3,
  excerpt: "Never say 'No' - offer an appropriate alternative.",
  why_shown:
    "The room was not ready, so what the guest asked for cannot be granted immediately. This principle governs the alternative you offer instead.",
};

const RESTAURANT_EVENT = /restaurant|table|food|meal|waiter|kitchen|order|missing|starter|dessert|drink|bar|serve|dinner|lunch|breakfast|waited|waiting/i;
const ROOM_EVENT = /room|check\s*-?\s*in|reception|front desk|lobby|not ready|key card|bellman|checkout|arrival|3\s*pm|late arrival/i;

/** The seed's processed debrief standard (today: the front-office room-not-ready
 * one, chunk-011). Read dynamically so plot edits in seed.ts flow through
 * without db.ts knowing names or numbers. */
function seedRoomStandard(): StandardReference | null {
  const seedDebrief = seedModule.diegoDebrief as
    | { standard: StandardReference | null }
    | undefined;
  return seedDebrief?.standard ?? null;
}

function resolveSopStandard(text: string): StandardReference | null {
  if (RESTAURANT_EVENT.test(text)) return { ...ALOUD_STANDARD };
  if (ROOM_EVENT.test(text)) return seedRoomStandard() ?? { ...FRONT_DESK_STANDARD };
  return null;
}

function debriefIncidentFor(
  text: string
): Debrief["incident"] {
  const restaurant = RESTAURANT_EVENT.test(text);
  const angry = /angry|furious|shouting|yelling/i.test(text);
  return {
    situation_type: restaurant
      ? /missing|starter|never arrived|forgot/i.test(text)
        ? "order_error"
        : "service_delay"
      : "room_not_ready",
    guest_emotion: angry ? "angry" : "frustrated",
    staff_actions: [],
    outcome: "unresolved",
    dimensions_touched: restaurant
      ? ["service_recovery", "empathy"]
      : ["service_recovery", "communication"],
  };
}

function generatedScenarioFor(text: string, scenarios: Scenario[]): string | null {
  if (RESTAURANT_EVENT.test(text)) {
    // F&B practice exists only as a shared starter (s3, A.L.O.U.D.) — nothing
    // was generated from this debrief, so no personal replay is claimed.
    return null;
  }
  const noise = /noise|23:00/i.test(text);
  if (noise) {
    const starter = scenarios.find(
      (s) => s.kind !== "personal" && /noise/i.test(`${s.title} ${s.description}`)
    );
    if (starter) return starter.id;
  }
  if (/not ready|check\s*-?\s*in|arrival|3\s*pm|key card/i.test(text)) {
    const personal = scenarios.find((s) => s.kind === "personal");
    if (personal) return personal.id;
    const starter = scenarios.find(
      (s) => s.kind !== "personal" && /not ready|check-?in/i.test(`${s.title} ${s.description}`)
    );
    if (starter) return starter.id;
  }
  return null;
}

// ── Store ────────────────────────────────────────────────────────────────────

const seedRecommendations = seedModule.recommendations as Recommendation[];

/** Ledger rebuilt from the seed's integer agreement counts (exact — rounding
 * rate × n would drift the first paint away from the seed copy). Every verify
 * from then on is a real recompute over stored verdicts. */
function seedLedger(): Map<BarsDimension, LedgerEntry> {
  const ledger = new Map<BarsDimension, LedgerEntry>();
  const seedCalibration = seedModule.calibration as {
    dimensions: Array<{
      dimension: BarsDimension;
      agreement_rate: number;
      agreements?: number;
      sample_size: number;
    }>;
  };
  for (const d of seedCalibration.dimensions) {
    const agreements =
      typeof d.agreements === "number"
        ? d.agreements
        : Math.max(
            0,
            Math.min(d.sample_size, Math.round(d.agreement_rate * d.sample_size))
          );
    ledger.set(d.dimension, { agreements, n: d.sample_size });
  }
  return ledger;
}

function calibrationDimensions(): CalibrationDimension[] {
  const entries: CalibrationReading[] = [];
  for (const dim of ALL_DIMENSIONS) {
    const entry = ledger.get(dim) ?? { agreements: 0, n: 0 };
    entries.push(computeReading(dim, entry));
  }
  return entries.map(
    (r) =>
      ({
        dimension: r.dimension,
        agreement_rate: r.agreement_rate ?? 0,
        sample_size: r.sample_size,
        wilson_low: r.lower ?? 0,
        wilson_high: r.upper ?? 0,
        state: r.state,
        advice: r.advice,
      }) as CalibrationDimension
  );
}

const ledger = seedLedger();

/**
 * The store lives on globalThis so dev's split module graphs (SSR pages vs
 * route handlers each load their own copy of this module) share ONE state —
 * the same single-instance behaviour a production build has anyway. Seeding
 * runs on every module load but is idempotent: runtime records use
 * runtime-only ids, so re-seeding never overwrites live state.
 */
interface MockStore {
  observations: Observation[];
  recommendations: Recommendation[];
  attempts: Map<string, AttemptRecord>;
  debriefs: Map<string, Debrief>;
  calibration: Calibration;
}

const globalForStore = globalThis as unknown as {
  __coachingMockStore?: MockStore;
};

/** True only on the very first module load — derived rows below append once. */
const storeWasJustCreated = !globalForStore.__coachingMockStore;

const store: MockStore =
  globalForStore.__coachingMockStore ??
  (globalForStore.__coachingMockStore = {
    observations: [...seedObservations] as Observation[],
    recommendations: [...seedRecommendations] as Recommendation[],
    attempts: new Map<string, AttemptRecord>(),
    debriefs: new Map<string, Debrief>(),
    calibration: {
      computed_at: new Date().toISOString(),
      dimensions: calibrationDimensions(),
    } as Calibration,
  });

// The 45 real attempts carry their own staff_id (roster-keyed by
// team-attempts.ts); the seeded in-progress personal replay belongs to the
// pinned staff-PWA actor. Map.set makes re-seeding on module reload a no-op.
for (const attempt of seedAttempts) {
  const stored: AttemptRecord = {
    ...attempt,
    staff_id: attempt.staff_id,
  };
  store.attempts.set(stored.id, stored);
}
store.attempts.set(seedModule.inProgressAttempt.id, {
  ...seedModule.inProgressAttempt,
  staff_id: staffPwaActor,
});

/** Per-scenario scoring templates discovered from seeded completed attempts.
 * Scenario → its own ScoreResult content, never a shared canned result. */
const scenarioTemplates = new Map<string, ScoreResult>();
for (const attempt of [...store.attempts.values()]) {
  if (attempt.status === "completed" && attempt.result) {
    scenarioTemplates.set(attempt.result.scenario_id, attempt.result);
  }
}
// Personal replay shares the 29 Aug check-in thread: anchored from seed so
// completing it scores on real anchors instead of the honest-null fallback.
if (seedModule.personalScoringAnchor) {
  scenarioTemplates.set(
    seedModule.personalScoringAnchor.scenario_id,
    seedModule.personalScoringAnchor
  );
}

// ── Derived pending recommendations (deterministic, from dataset rows) ──────
// Four findings join the queue once per store creation (not per module load —
// dev's split module graphs share the globalThis store): ok rows in
// blocked|skill_gap with the largest |gap|, at most one per staff, staff-001
// excluded (Diego's own finding r91a already leads the queue). Every row this
// rule picks today is blocked, so all four classify as policy. Ids carry the
// staff's latest observation date; trace ids are fixed per candidate so the
// seeded queue is byte-for-byte restorable.

const FINDING_TRACE_SUFFIX = ["3P", "4Q", "5R", "6S"];

function staffNameOf(rosterId: string): string {
  const member = seedStaffMembers.find((s) => s.id === rosterId);
  return member?.name ?? rosterId;
}

/** Lower-case copy label, matching the app's own phrasing in rec bodies. */
function dimensionCopyLabel(dimension: BarsDimension): string {
  return dimension === "service_recovery" ? "service recovery" : dimension;
}

function latestObservationDateOf(rosterId: string): string {
  const latest = [...store.observations]
    .filter((o) => o.staff_id === rosterId)
    .sort((a, b) =>
      (b.observed_at ?? b.created_at).localeCompare(a.observed_at ?? a.created_at)
    )[0];
  return (latest?.observed_at ?? latest?.created_at ?? "").slice(0, 10);
}

/** Most recent completed attempt of this staff member quoting the dimension. */
function latestEvidenceFor(
  rosterId: string,
  dimension: BarsDimension
): EvidenceSpan & { attempt_id: string } | null {
  const completed = [...store.attempts.values()]
    .filter(
      (a) => a.staff_id === rosterId && a.status === "completed" && a.result
    )
    .sort((a, b) =>
      (b.result?.completed_at ?? "").localeCompare(a.result?.completed_at ?? "")
    );
  for (const attempt of completed) {
    const evidence = attempt.result?.evidence.find(
      (e) => e.dimension === dimension && e.quote
    );
    if (evidence) {
      return { ...evidence, attempt_id: attempt.id };
    }
  }
  return null;
}

/** Latest floor observation rating the dimension, with that rating's level. */
function latestFloorReadingFor(rosterId: string, dimension: BarsDimension) {
  const latest = [...store.observations]
    .filter(
      (o) =>
        o.staff_id === rosterId &&
        o.ratings.some((r) => r.dimension === dimension && r.level !== null)
    )
    .sort((a, b) =>
      (b.observed_at ?? b.created_at).localeCompare(a.observed_at ?? a.created_at)
    )[0];
  if (!latest) return null;
  const level = latest.ratings.find((r) => r.dimension === dimension)?.level;
  return { observation: latest, level: level ?? null };
}

function seededPendingRecommendations(): Recommendation[] {
  const candidates = seedModule.TEAM_GAP_ROWS.filter(
    (r) =>
      r.status === "ok" &&
      (r.quadrant === "blocked" || r.quadrant === "skill_gap") &&
      r.gap !== null &&
      r.gap > 0 &&
      r.practice_mean !== null &&
      r.floor_mean !== null &&
      r.staff_id !== "staff-001"
  );
  const bestPerStaff = new Map<string, TeamGapRow>();
  for (const candidate of candidates) {
    const current = bestPerStaff.get(candidate.staff_id);
    if (!current || Math.abs(candidate.gap!) > Math.abs(current.gap!)) {
      bestPerStaff.set(candidate.staff_id, candidate);
    }
  }
  return [...bestPerStaff.values()]
    .sort(
      (a, b) =>
        Math.abs(b.gap!) - Math.abs(a.gap!) ||
        a.staff_id.localeCompare(b.staff_id)
    )
    .slice(0, 4)
    .map((row, index) => {
      const rosterId = rosterIdOf(row.staff_id);
      const dimension = row.dimension;
      const lower = dimensionCopyLabel(dimension);
      const latestDate = latestObservationDateOf(rosterId);
      const name = staffNameOf(rosterId);
      const blocked = row.quadrant === "blocked";
      const classification: Recommendation["classification"] = blocked
        ? "policy"
        : "behavioural";

      const citations: Recommendation["citations"] = [];
      const evidence = latestEvidenceFor(rosterId, dimension);
      if (evidence) {
        citations.push({
          kind: "attempt_turn",
          claim: `showed ${lower} in a completed practice run`,
          source_ref: `attempt:${evidence.attempt_id}:turn:${evidence.turn_index}`,
          quoted_span: evidence.quote,
        });
      }
      const floor = latestFloorReadingFor(rosterId, dimension);
      if (floor) {
        citations.push({
          kind: "observation",
          claim: `the live ${lower} exchange on ${floor.observation.observed_at.slice(0, 10)} scored ${floor.level}`,
          source_ref: `observation:${floor.observation.id}:ratings:${dimension}`,
          quoted_span: floor.observation.what_happened,
        });
      }
      citations.push({
        kind: "metric",
        claim: `a transfer gap on ${lower}, the floor trails practice`,
        source_ref: `metric:gap:${dimension}`,
      });

      const entry = ledger.get(dimension) ?? { agreements: 0, n: 0 };
      const reading = computeReading(dimension, entry);
      return {
        id: `rec-${rosterId}-${latestDate}`,
        status: "pending_verify" as const,
        staff_id: rosterId,
        classification,
        headline: blocked
          ? `${name} performs ${lower} in practice and drops it on the floor.`
          : `${name}'s ${lower} is still building, in practice and on the floor.`,
        body: blocked
          ? "The skill demonstrably exists in practice; on the floor it did not appear. That points at authority or pressure, not a training gap, more practice would miss the point."
          : "Neither stream shows the skill yet, this is the one case where practice is the answer.",
        suggested_action: blocked
          ? `Confirm what ${name} believes they are allowed to do on ${lower} and what the floor pressure was. Do not assign further practice.`
          : `Assign the starter scenario on ${lower} this week and review the evidence spans together.`,
        calibration: {
          dimension,
          agreement_rate: reading.agreement_rate ?? 0,
          sample_size: reading.sample_size,
          advice: reading.advice,
        },
        citations,
        trace_id: `01J9Z2K8QW${FINDING_TRACE_SUFFIX[index] ?? "7Z"}`,
        created_at: `${latestDate}T12:00:00Z`,
      };
    });
}

if (storeWasJustCreated) {
  store.recommendations = [
    ...store.recommendations,
    ...seededPendingRecommendations(),
  ];
}

// ── Team insights (computed from the same dataset rows) ─────────────────────
// Each dimension with k = 5 or more staff carrying a blocked/skill_gap
// finding becomes a pattern; the plurality quadrant sets classification
// (blocked → policy, skill_gap → behavioural) and routing.py's cohort rules
// pick the route. Dims with findings under k are suppressed.

const INSIGHT_K = 5;

function computeTeamInsights(): TeamInsights {
  const obsDates = seedObservations.map((o) => o.observed_at ?? o.created_at);
  const attemptDates = seedAttempts.flatMap((a) =>
    a.result ? [a.result.completed_at] : []
  );
  const allDates = [...obsDates, ...attemptDates].sort();
  const window = {
    start: [...obsDates].sort()[0] ?? allDates[0] ?? "",
    end: allDates[allDates.length - 1] ?? "",
  };

  const patterns: TeamInsights["patterns"] = [];
  let suppressedCount = 0;
  for (const dimension of ALL_DIMENSIONS) {
    const staff = seedModule.findingStaffIds(seedModule.TEAM_GAP_ROWS, dimension);
    if (staff.length === 0) continue;
    if (staff.length < INSIGHT_K) {
      suppressedCount += 1;
      continue;
    }
    const findings = seedModule.TEAM_GAP_ROWS.filter(
      (r) => r.dimension === dimension && staff.includes(r.staff_id)
    );
    const policyCount = findings.filter((r) => r.quadrant === "blocked").length;
    const classification: Recommendation["classification"] =
      policyCount >= findings.length - policyCount ? "policy" : "behavioural";
    const policyLead = classification === "policy";
    const n = staff.length;
    const lower = dimensionCopyLabel(dimension);
    patterns.push({
      id: `cp0${patterns.length + 1}-${dimension}`,
      classification,
      staff_count: n,
      dimension,
      description: policyLead
        ? `${n} staff keep ${lower} in practice and lose it live, the same blocked pattern across the team. That is procedure or authority, not ${n} behavioural problems.`
        : `${n} staff sit at or under the floor bar on ${lower} in both practice and live work, the skill is still building for the cohort.`,
      suggested_action: policyLead
        ? `Set and communicate the ${lower} standard and the discretionary limit once, no individual practice.`
        : `Assign targeted practice on ${lower} to the cohort, then re-observe the same staff next shift.`,
      route: policyLead ? "operations" : "manager",
      detected_at: `${window.end}T09:30:00Z`,
    });
  }

  return {
    window,
    k_threshold: INSIGHT_K,
    patterns,
    suppressed:
      suppressedCount > 0
        ? [{ reason: "below_k_threshold", count: suppressedCount }]
        : [],
  };
}

const traceId = () =>
  Array.from({ length: 12 }, () =>
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[Math.floor(Math.random() * 36)]
  ).join("");

// ── Recommendation drafting (cite-gate style: practice + floor + metric) ─────

function latestAttemptEvidence(
  dimension: BarsDimension
): { quote: string; turn_index: number; attempt_id: string } | null {
  const completed = [...store.attempts.values()]
    .filter((a) => a.status === "completed" && a.result)
    .sort(
      (a, b) =>
        new Date(b.result?.completed_at ?? 0).getTime() -
        new Date(a.result?.completed_at ?? 0).getTime()
    );
  for (const attempt of completed) {
    if (!attempt.result) continue;
    const evidence = attempt.result.evidence.find(
      (e) => e.dimension === dimension && e.quote
    );
    if (evidence) {
      return {
        quote: evidence.quote,
        turn_index: evidence.turn_index,
        attempt_id: attempt.id,
      };
    }
  }
  return null;
}

function staffToken(staffId: string): string {
  const last = staffId.split("-").pop();
  return last && last.length > 0 ? last : staffId;
}

function buildRecommendationForObservation(
  observation: Observation,
  gapReadings: GapReading[]
): Recommendation {
  const now = new Date().toISOString();
  const staff = observation.staff_id;
  const observedDims = observation.ratings
    .filter((r) => r.level !== null)
    .map((r) => r.dimension as BarsDimension);

  const readable = gapReadings.filter(
    (g) => g.quadrant !== null && observedDims.includes(g.dimension)
  );
  const calibrationEntry = ledger.get(readable[0]?.dimension ?? observedDims[0] ?? "service_recovery") ?? { agreements: 0, n: 0 };
  const dim = readable[0]?.dimension ?? observedDims[0] ?? "service_recovery";

  const calibrationInfo = {
    dimension: dim,
    agreement_rate: calibrationEntry.n > 0 ? computeReading(dim, calibrationEntry).agreement_rate ?? 0 : 0,
    sample_size: calibrationEntry.n,
    advice:
      calibrationEntry.n > 0
        ? computeReading(dim, calibrationEntry).advice
        : "Not yet measured on this dimension.",
  };

  if (readable.length === 0) {
    // No practice history → the agent abstains and says what is missing
    // (cite-gate: a transfer-gap recommendation needs both streams).
    const labelled = observedDims.length > 0 ? observedDims.join(", ") : "this dimension";
    return {
      id: `rec-${staffToken(staff)}-${Date.now()}`,
      status: "abstained",
      staff_id: staff,
      classification: "behavioural",
      headline: "Not enough evidence yet for grounded coaching.",
      body: `The observation is logged on ${labelled}, but there is no practice history to compare it against. A transfer-gap reading needs both streams, ask for a practice run, then observe again.`,
      suggested_action: "",
      calibration: calibrationInfo,
      citations: [],
      trace_id: traceId(),
      created_at: now,
    };
  }

  const primary = [...readable].sort((a, b) => {
    // Prefer a blocked finding with evidence behind it — that is the signal a
    // manager acts on; fall back to the largest gap.
    const aEvidence = latestAttemptEvidence(a.dimension) ? 1 : 0;
    const bEvidence = latestAttemptEvidence(b.dimension) ? 1 : 0;
    if (a.quadrant === "blocked" && b.quadrant !== "blocked") return -1;
    if (b.quadrant === "blocked" && a.quadrant !== "blocked") return 1;
    const aGap = (a.practiceMean ?? 0) - (a.floorMean ?? 0);
    const bGap = (b.practiceMean ?? 0) - (b.floorMean ?? 0);
    if (bEvidence !== aEvidence) return bEvidence - aEvidence;
    return bGap - aGap;
  })[0];

  const classification =
    primary.quadrant === "blocked"
      ? ("policy" as const)
      : primary.quadrant === "recalibrate"
        ? ("process" as const)
        : ("behavioural" as const);

  const dimLabel =
    primary.dimension === "service_recovery"
      ? "Service recovery"
      : primary.dimension;

  const template =
    primary.quadrant === "blocked"
      ? {
          headline:
            "They performed this in practice and did not on the floor. That points at authority or pressure, not a training gap.",
          body: `${dimLabel}, practice looks fine here; on the floor it did not appear. More practice would miss the point.`,
          suggested_action:
            "Confirm what this person believes they are allowed to offer and what the floor pressure was. Do not assign further practice.",
        }
      : primary.quadrant === "skill_gap"
        ? {
            headline:
              "Practice and floor both show this skill still building, targeted practice is the right next step.",
            body: `${dimLabel}, neither stream shows the skill yet. This is the one case where practice is the answer.`,
            suggested_action:
              "Assign the starter scenario for this dimension this week and review the evidence spans together.",
          }
        : primary.quadrant === "recalibrate"
          ? {
              headline:
                "Strong on the floor but weak in practice, check the rubric and the scenario, not the person.",
              body: `${dimLabel}, when the floor runs ahead of practice, it is usually a signal about our scoring.`,
              suggested_action:
                "Review the rubric anchors and the practice scenario before coaching the person.",
            }
          : {
              headline:
                "Practice is transferring to the floor on this dimension.",
              body: `${dimLabel}, practice and the floor align. The skill is holding under real conditions.`,
              suggested_action:
                "Stretch them: use them as a peer coach or promote the behaviour in the next briefing.",
            };

  const citations: Recommendation["citations"] = [];
  const evidence = latestAttemptEvidence(primary.dimension);
  if (evidence) {
    citations.push({
      kind: "attempt_turn",
      claim: `demonstrated ${primary.dimension.replace("_", " ")} in practice`,
      source_ref: `attempt:${evidence.attempt_id}:turn:${evidence.turn_index}`,
      quoted_span: evidence.quote,
    });
  } else {
    const practiceDate =
      [...store.attempts.values()]
        .filter((a) => a.status === "completed" && a.result)
        .sort(
          (a, b) =>
            new Date(b.result?.completed_at ?? 0).getTime() -
            new Date(a.result?.completed_at ?? 0).getTime()
        )[0]?.result?.completed_at ?? null;
    citations.push({
      kind: "attempt_turn",
      claim: `practised this dimension in simulation${practiceDate ? ` on ${practiceDate.slice(0, 10)}` : ""}`,
      source_ref: "metric:practice_history",
    });
  }
  citations.push({
    kind: "observation",
    claim: `floor observation on ${observation.observed_at.slice(0, 10)}`,
    source_ref: `obs:${observation.id}:what_happened`,
    quoted_span: observation.what_happened,
  });
  if (primary.practiceMean !== null && primary.floorMean !== null) {
    const lowerDim = dimensionCopyLabel(primary.dimension);
    const claim =
      primary.quadrant === "competent"
        ? `practice and the floor align on ${lowerDim}, no transfer gap`
        : primary.quadrant === "recalibrate"
          ? `a transfer gap on ${lowerDim}, practice trails the floor`
          : `a transfer gap on ${lowerDim}, the floor trails practice`;
    citations.push({
      kind: "metric",
      claim,
      source_ref: `metric:gap:${primary.dimension}`,
    });
  }
  if (primary.quadrant === "blocked" && primary.dimension === "service_recovery") {
    const standard = seedRoomStandard() ?? { ...FRONT_DESK_STANDARD };
    citations.push({
      kind: "sop_chunk",
      claim: "your complaint standard takes you through what the guest expects before any remedy",
      source_ref: `sop:chunk-${standard.chunk_id}`,
      quoted_span: standard.excerpt,
    });
  }

  return {
    id: `rec-${staffToken(staff)}-${Date.now()}`,
    status: "pending_verify",
    staff_id: staff,
    classification,
    headline: template.headline,
    body: template.body,
    suggested_action: template.suggested_action,
    calibration: calibrationInfo,
    citations,
    trace_id: traceId(),
    created_at: now,
  };
}

// ── Public mock API ──────────────────────────────────────────────────────────

export const mockDb = {
  // GET /scenarios
  async listScenarios(): Promise<Scenario[]> {
    await wait(250);
    return seedModule.scenarios as Scenario[];
  },

  // POST /scenarios/{id}/attempts — idempotent per scenario: an in-progress
  // attempt is reused so refreshes never lose the conversation. The opener is
  // the scenario's own script (see seed.guestScripts), never a shared line.
  async startAttempt(scenarioId: string): Promise<PracticeAttempt> {
    await wait(350);
    const existing = [...store.attempts.values()].find(
      (a) => a.scenario_id === scenarioId && a.status === "in_progress"
    );
    if (existing) return cloneAttempt(existing);

    const script = guestScriptFor(scenarioId);
    const opener = script?.opener ?? UNSCRIPTED_OPENERS[0];
    const attempt: AttemptRecord = {
      id: `attempt-${Date.now()}`,
      scenario_id: scenarioId,
      // Runtime practice is launched from the staff PWA, whose single actor is
      // pinned by seed.ts (see the attribution note above).
      staff_id: staffPwaActor,
      status: "in_progress",
      turns: [
        {
          turn_index: 0,
          guest: { content: opener.content, mood: opener.mood },
          turns_remaining: script?.replies.length ?? 4,
          can_complete: false,
        },
      ],
      result: null,
    };
    store.attempts = new Map(store.attempts).set(attempt.id, attempt);
    return cloneAttempt(attempt);
  },

  // POST /attempts/{id}/turns — the guest answers from the attempt's own
  // scenario script, one reply per staff turn; no cross-scenario reuse.
  async sendTurn(attemptId: string, content: string) {
    await wait(600);
    const attempt = store.attempts.get(attemptId);
    if (!attempt) throw new Error("Attempt not found");
    const turnIndex = attempt.turns.length;
    const script = guestScriptFor(attempt.scenario_id);
    const totalTurns = script?.replies.length ?? 4;
    const turnsRemaining = totalTurns - (turnIndex - 1);

    const staffTurnIndex = Math.max(0, turnIndex - 1); // opener is turn 0
    const guestLine =
      script && script.replies.length > 0
        ? script.replies[Math.min(staffTurnIndex, script.replies.length - 1)]
        : UNSCRIPTED_REPLIES[staffTurnIndex % UNSCRIPTED_REPLIES.length];

    const turnResponse: TurnResponse = {
      turn_index: turnIndex,
      guest: { content: guestLine.content, mood: guestLine.mood },
      turns_remaining: Math.max(turnsRemaining, 0),
      can_complete: turnsRemaining <= 0,
    };

    store.attempts = new Map(store.attempts).set(attemptId, {
      ...attempt,
      turns: [...attempt.turns, turnResponse],
    });
    return turnResponse;
  },

  // POST /attempts/{id}/complete → GET /attempts/{id}
  async completeAttempt(attemptId: string): Promise<ScoreResult> {
    await wait(900);
    const attempt = store.attempts.get(attemptId);
    if (!attempt) throw new Error("Attempt not found");

    const template = scenarioTemplates.get(attempt.scenario_id);
    const scenario = (seedModule.scenarios as Scenario[]).find(
      (s) => s.id === attempt.scenario_id
    );
    const now = new Date().toISOString();

    const result: ScoreResult = template
      ? {
          ...template,
          attempt_id: attemptId,
          scenario_id: attempt.scenario_id,
          completed_at: now,
        }
      : {
          // Honest fallback: this scenario has no calibrated scoring anchors
          // in the store yet, so nothing is scored rather than guessed.
          attempt_id: attemptId,
          scenario_id: attempt.scenario_id,
          completed_at: now,
          scores: (scenario?.dimensions ?? ALL_DIMENSIONS).map((dimension) => ({
            dimension,
            level: null,
          })),
          evidence: [],
          overall_feedback:
            "This scenario has no scoring anchors loaded yet, so no dimension is scored rather than guessed. Once the scenario's rubric is loaded, completing it again will produce a real reading.",
        };

    store.attempts = new Map(store.attempts).set(attemptId, {
      ...attempt,
      status: "completed",
      result,
    });
    return result;
  },

  async getAttempt(attemptId: string): Promise<AttemptRecord | undefined> {
    await wait(150);
    const found = store.attempts.get(attemptId);
    if (found) return cloneAttempt(found);
    // Legacy narrative runs the staff history page links to (8a4e-diego,
    // 3f7b-aug29, 4c8d-aug26, 7b3c-…). Display-only: they stay out of the
    // attempts map, so practice aggregates never count them twice.
    const legacy = seedModule.legacyNarrativeAttempts as
      | PracticeAttempt[]
      | undefined;
    const match = legacy?.find((a) => a.id === attemptId);
    return match ? cloneAttempt({ ...match, staff_id: staffPwaActor }) : undefined;
  },

  // GET /staff/{id}/scores support — the full attempt history (practice
  // stream) as immutable snapshots; callers filter by staff_id themselves.
  // Runtime attempts are stored with staff_id, so practice history is real,
  // not inferred from the seed module.
  async listAttempts(): Promise<AttemptRecord[]> {
    await wait(150);
    return [...store.attempts.values()].map(cloneAttempt);
  },

  // GET /debriefs/{id}
  async getDebrief(id: string): Promise<Debrief | undefined> {
    await wait(250);
    const found = store.debriefs.get(id);
    if (found) return found;
    const seedDebrief = seedModule.diegoDebrief as Debrief | undefined;
    return seedDebrief && seedDebrief.id === id ? seedDebrief : undefined;
  },

  // POST /debriefs — registers a debrief, resolved synchronously to the
  // contract's DebriefStatus vocabulary (uploaded → extracted; failed when no
  // clause matches).
  async createDebrief(text: string): Promise<{ id: string; debrief: Debrief }> {
    await wait(700);
    const id = `d-${Date.now()}`;
    const scenarioId = generatedScenarioFor(text, seedModule.scenarios as Scenario[]);
    const standard = resolveSopStandard(text);
    const debrief: Debrief = {
      id,
      status: standard ? "extracted" : "failed",
      transcript: text,
      incident: standard ? debriefIncidentFor(text) : null,
      standard,
      generated_scenario_id: standard ? scenarioId : null,
    };
    store.debriefs = new Map(store.debriefs).set(id, debrief);
    return { id, debrief };
  },

  // POST /observations (Listing 5) — unlocks practice history and drafts a
  // real recommendation into the verify queue.
  async logObservation(input: ObservationInput): Promise<ObservationResponse> {
    await wait(800);
    if (!knownStaffIds.has(input.staff_id)) {
      throw new Error("Unknown staff member: log an observation for a staff member on the roster");
    }
    if (!Array.isArray(input.ratings) || input.ratings.length === 0) {
      throw new Error("An observation needs at least one rated dimension");
    }

    const observation: Observation = {
      ...input,
      id: `obs-${Date.now()}`,
      created_at: new Date().toISOString(),
    };
    store.observations = [...store.observations, observation];

    const gapReadings = computeGapFor(input.staff_id);
    const recommendation = buildRecommendationForObservation(observation, gapReadings);
    store.recommendations = [recommendation, ...store.recommendations];

    return {
      id: observation.id,
      unlocked_practice_history: true,
      recommendation_id: recommendation.id,
      recommendation_status:
        recommendation.status === "abstained" ? "abstained" : "pending_verify",
    };
  },

  async listObservations(): Promise<Observation[]> {
    await wait(200);
    return store.observations.map(cloneObservation);
  },

  // GET /staff/{id}/gap (Listing 6) — the dataset's own transfer-gap rows
  // (transfer_gaps.json served verbatim through buildTransferGap), with
  // weekly trend series derived from the stored practice/floor streams.
  async getGap(staffId: string): Promise<TransferGap | undefined> {
    await wait(400);
    if (!knownStaffIds.has(staffId)) return undefined;
    return buildTransferGap(staffId);
  },

  // GET /recommendations — the verify queue
  async listRecommendations(): Promise<Recommendation[]> {
    await wait(300);
    return store.recommendations.map((r) => structuredClone(r));
  },

  async getRecommendation(id: string): Promise<Recommendation | undefined> {
    await wait(200);
    const found = store.recommendations.find((r) => r.id === id);
    return found ? structuredClone(found) : undefined;
  },

  // POST /recommendations/{id}/verify (Listing 9) — records the verdict and
  // recomputes calibration from stored verdicts (calibration.py), then routes
  // the confirmed finding (routing.py, first match wins).
  async verifyRecommendation(
    id: string,
    input: VerifyInput
  ): Promise<VerifyResponse> {
    await wait(700);
    const verdicts = ["confirmed", "corrected", "rejected"] as const;
    if (!verdicts.includes(input.verdict as (typeof verdicts)[number])) {
      throw new Error(`verdict must be one of ${verdicts.join(", ")}`);
    }
    const rec = store.recommendations.find((r) => r.id === id);
    if (!rec) throw new Error("Recommendation not found");

    store.recommendations = store.recommendations.map((r) =>
      r.id === id ? { ...r, status: input.verdict } : r
    );

    // 1. Record the verdict on the dimension ledger (binary agreement:
    // confirmed agrees; corrected and rejected do not — matches the real
    // calibration input of agreements / n).
    const dimension = (Array.isArray(rec.calibration)
      ? rec.calibration[0]?.dimension
      : rec.calibration.dimension) as BarsDimension;
    const beforeEntry = ledger.get(dimension) ?? { agreements: 0, n: 0 };
    const agrees = input.verdict === "confirmed";
    const afterEntry: LedgerEntry = {
      agreements: beforeEntry.agreements + (agrees ? 1 : 0),
      n: beforeEntry.n + 1,
    };
    ledger.set(dimension, afterEntry);

    // 2. Recompute every dimension from the ledger.
    store.calibration = {
      ...store.calibration,
      computed_at: new Date().toISOString(),
      dimensions: calibrationDimensions(),
    };

    const before = computeReading(dimension, beforeEntry);
    const after = computeReading(dimension, afterEntry);

    // 3. Routing. A rejected finding is not escalated at all; anything routed
    // only to the default coaching conversation (manager, severity 1) is
    // recorded but not surfaced as an escalation.
    let escalation: Escalation | null = null;
    if (input.verdict !== "rejected") {
      const floorLevels = store.observations
        .filter((o) => o.staff_id === rec.staff_id)
        .flatMap((o) =>
          o.ratings
            .filter((r) => r.dimension === dimension && r.level !== null)
            .map((r) => r.level as number)
        );
      const floorMean =
        floorLevels.length > 0
          ? floorLevels.reduce((a, b) => a + b, 0) / floorLevels.length
          : null;
      const decision = routeFinding({
        classification: rec.classification,
        cohort_size: cohortFor(dimension),
        floor_mean: floorMean,
        floor_n: floorLevels.length,
        floor_trend_slope: floorTrendSlope(rec.staff_id, dimension),
        days_since_activity: 0,
      });
      if (decision) {
        escalation = {
          id: `esc-${Date.now()}`,
          route: decision.route,
          severity: decision.severity,
          rule_id: decision.rule_id,
          summary: decision.summary,
        } as unknown as Escalation;
      }
    }

    const calibrationUpdated = {
      dimension,
      agreement_rate_before: before.agreement_rate ?? 0,
      agreement_rate_after: after.agreement_rate ?? 0,
      sample_size: after.sample_size,
      lower: after.lower ?? null,
      upper: after.upper ?? null,
      state: after.state,
      advice: after.advice,
    };

    return {
      status: input.verdict,
      calibration_updated: calibrationUpdated,
      escalation,
    };
  },

  // GET /calibration
  async getCalibration(): Promise<Calibration> {
    await wait(250);
    return store.calibration;
  },

  // GET /insights/team (Listing 10) — patterns derived from the dataset's
  // transfer-gap rows (see computeTeamInsights).
  async getTeamInsights(): Promise<TeamInsights> {
    await wait(400);
    return computeTeamInsights();
  },
};
