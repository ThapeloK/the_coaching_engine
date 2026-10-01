/**
 * Type definitions mirroring the frozen API contracts (LLD-B, v1.0, 30 Aug 2026).
 * Base path: /api/v1 · Auth: Bearer JWT · Errors: RFC 9457 problem+json.
 */

// ── BARS scoring ────────────────────────────────────────────────────────────

export type BarsDimension =
  | "empathy"
  | "anticipation"
  | "communication"
  | "composure"
  | "service_recovery";

/** Floor observation uses the same five BARS dimensions — one vocabulary, no drift. */
export type ObservationDimension = BarsDimension;

// ── People ───────────────────────────────────────────────────────────────────

export interface StaffMember {
  id: string;
  name: string;
  role: string;
  department: string;
  started_at: string;
}

// ── Debrief (Master Doc steps 1–3) ──────────────────────────────────────────

export interface Incident {
  situation_type: string;
  guest_emotion: string;
  staff_actions: string[];
  outcome: string;
  dimensions_touched: BarsDimension[];
}

export interface StandardReference {
  chunk_id: string;
  document: string;
  section_path: string;
  step_number: number;
  excerpt: string;
  why_shown: string;
}

/** Frozen DebriefStatus enum (openapi.yaml). */
export type DebriefStatus =
  | "uploaded"
  | "transcribed"
  | "redacted"
  | "extracted"
  | "failed";

/** What the system understood, when the debrief was not given in English.
 *
 * Present only on a translated debrief. It carries the speaker's own sentence
 * and the regional terms that were looked up to translate it, so the person
 * can check that what was understood is what they meant. Not persisted yet:
 * the client holds it for the session, so it shows once rather than in the
 * staff member's history.
 */
export interface HeardReading {
  original: string;
  language: string;
  country: string | null;
  terms: Array<{
    term: string;
    gloss: string;
    countries: string[];
    ambiguous: boolean;
  }>;
}

export interface Debrief {
  id: string;
  status: DebriefStatus;
  transcript: string | null;
  incident: Incident | null;
  standard: StandardReference | null;
  /** Legacy demo field — the real API returns it from the agent graph, not the debrief row. */
  generated_scenario_id: string | null;
  /** Attached by the client from the create response; never read from the row. */
  heard?: HeardReading;
}

/** POST /debriefs request body. Contract requires upload_key/duration_ms/recorded_at
 * for voice uploads; `text` is the legacy typed-debrief field the staff PWA still sends. */
export interface DebriefInput {
  upload_key?: string;
  duration_ms?: number;
  recorded_at?: string;
  text?: string;
}

/** POST /debriefs → 202 body (openapi.yaml). */
export interface DebriefRegistration {
  id: string;
  status: DebriefStatus;
  poll_after_ms: number;
  heard?: HeardReading;
}

// ── Practice (Master Doc steps 4–5) ─────────────────────────────────────────

export interface Scenario {
  id: string;
  title: string;
  description: string;
  kind: "starter" | "personal";
  source_debrief_id: string | null;
  dimensions: BarsDimension[];
  duration_minutes: number;
}

export interface GuestTurn {
  content: string;
  mood: "neutral" | "frustrated" | "escalating" | "calming";
  /** Content hash of the synthesised line, when speech was available.
   * Absent is normal: the conversation is designed to work as text. */
  audio_id?: string;
}

export interface TurnResponse {
  turn_index: number;
  guest: GuestTurn;
  turns_remaining: number;
  can_complete: boolean;
}

export interface EvidenceSpan {
  dimension: BarsDimension;
  quote: string;
  turn_index: number;
  explains: string;
}

export interface ScoreResult {
  attempt_id: string;
  scenario_id: string;
  completed_at: string;
  scores: Array<{ dimension: BarsDimension; level: number | null }>;
  evidence: EvidenceSpan[];
  overall_feedback: string;
}

export interface PracticeAttempt {
  id: string;
  scenario_id: string;
  status: "in_progress" | "completed";
  turns: TurnResponse[];
  result: ScoreResult | null;
}

// ── Observation (Master Doc step 6) ─────────────────────────────────────────

export interface ObservationRating {
  dimension: ObservationDimension;
  level: number | null;
}

export interface ObservationInput {
  staff_id: string;
  observed_at: string;
  context: string;
  what_happened: string;
  ratings: ObservationRating[];
}

export interface Observation extends ObservationInput {
  id: string;
  created_at: string;
}

/** A rating the extractor proposed, with the manager's own words that
 * support it and where those words sit in the transcript. A rating whose
 * quote is not in the transcript never reaches the browser. */
export interface DraftRating {
  dimension: ObservationDimension;
  level: number;
  quote: string;
  /** [start, end) character offsets into the transcript, for highlighting. */
  span: [number, number];
}

/** Who the extractor thinks the manager was talking about. Never a guess
 * between two people: two Marias come back as "ambiguous" with both. */
export interface DraftPerson {
  status: "matched" | "ambiguous" | "unmatched";
  spoken: string;
  staff_id?: string;
  name?: string;
  candidates?: Array<{ staff_id: string; name: string; department?: string }>;
}

/** One proposed observation. Nothing is written until the manager confirms. */
export interface ObservationDraft {
  person: DraftPerson;
  moment: "guest_question" | "complaint" | "proactive" | "routine";
  scope: "full" | "partial";
  what_happened: string;
  ratings: DraftRating[];
  /** True when the words could not be tied to any dimension. The person was
   * still mentioned, so the draft is shown rather than silently dropped. */
  needs_rating: boolean;
}

export interface ObservationDraftResponse {
  transcript: string;
  drafts: ObservationDraft[];
  /** Ratings the model proposed and could not point at. Shown to the manager,
   * because "I threw two of these away" is the honest version. */
  dropped_ratings: number;
  detail?: string;
}

/** What comes back from commissioning the weekly brief.
 *
 * Manus is asynchronous by design: the work takes minutes, so the API hands
 * back a handle rather than a document, and the finished brief lives on Manus
 * rather than in our database. The UI has to be honest about that instead of
 * pretending to have a result.
 */
/** The brief itself, polled while Manus writes it.
 *
 * "running" is a normal answer, not an error: the agent takes minutes and the
 * console asks repeatedly until there is a document.
 */
export interface WeeklyBrief {
  /** "none" when the property has never commissioned one; "unreachable" when
   * the task id is on record but Manus did not answer just now. */
  status: "running" | "ready" | "empty" | "none" | "unreachable";
  task_id?: string;
  /** When it was commissioned, from the audit trail. */
  commissioned_at?: string;
  patterns_included?: number;
  /** The agent's closing note. Present before the document sometimes is. */
  summary?: string;
  /** The brief, as markdown. Only on "ready". */
  markdown?: string;
  filename?: string;
}

export interface WeeklyBriefResponse {
  status: "submitted" | "nothing_to_report";
  patterns_included?: number;
  task_id?: string;
  task_url?: string;
  detail?: string;
}

export interface ObservationResponse {
  id: string;
  unlocked_practice_history: boolean;
  recommendation_id: string;
  recommendation_status: "generating" | "pending_verify" | "abstained";
}

// ── Staff score history (GET /staff/{id}/scores) ─────────────────────────────

export type ScoreSource = "practice" | "floor";

/** One dimension scored from one evidence stream (one attempt, one observation). */
export interface StaffScoreRow {
  /** Evidence-scoped id: `<attempt-id|observation-id>:<dimension>`. */
  id: string;
  source: ScoreSource;
  dimension: BarsDimension;
  /** 1..5, or null when the dimension was not evidenced. */
  level: number | null;
  /** Attempt completion time (practice) or the observed moment (floor). */
  recorded_at: string;
  /** Practice: the quoted turn that anchored the level. Floor: what_happened. */
  evidence_span: string | null;
}

/** GET /staff/{id}/scores → 200 body (openapi.yaml, `?source=practice|floor`). */
export interface ScoresResponse {
  staff_id: string;
  source: ScoreSource;
  scores: StaffScoreRow[];
}

// ── Transfer gap (Master Doc steps 9–10) ────────────────────────────────────

export type Quadrant = "competent" | "skill_gap" | "blocked" | "recalibrate";

export interface GapDimension {
  dimension: BarsDimension;
  practice_mean: number;
  practice_n: number;
  floor_mean: number;
  floor_n: number;
  gap: number;
  quadrant: Quadrant;
  reading: string;
  trend: Array<{ week: string; gap: number }>;
}

export interface TransferGap {
  staff_id: string;
  computed_at: string;
  dimensions: GapDimension[];
  insufficient_evidence: ObservationDimension[];
}

// ── Recommendation & verification (Master Doc steps 7–8, 12–14) ─────────────

export type Classification = "behavioural" | "process" | "policy";

/** Frozen escalation/insight route enum (openapi.yaml) — note `ld_hr`, not `ld`. */
export type EscalationRoute = "manager" | "ld_hr" | "operations";

export interface Citation {
  kind: "attempt_turn" | "observation" | "sop_chunk" | "rubric_anchor" | "metric";
  claim: string;
  source_ref: string;
  quoted_span?: string;
}

export interface CalibrationInfo {
  dimension: BarsDimension;
  agreement_rate: number;
  sample_size: number;
  advice: string;
  /** Contract fields — optional until the agent pipeline populates them. */
  lower?: number | null;
  upper?: number | null;
  state?: CalibrationState;
}

export interface Recommendation {
  id: string;
  status: "pending_verify" | "confirmed" | "corrected" | "rejected" | "abstained";
  staff_id: string;
  /** The server resolves the display name; absent in mock mode, where the
   * seed roster answers instead. */
  staff_name?: string;
  /** Null when the agent abstained: there is no classification to make. */
  classification: Classification | null;
  headline: string;
  body: string;
  suggested_action: string;
  /** The server sends one reading per scored dimension; the mock sends a
   * single object. Read it through `primaryCalibration` rather than
   * dereferencing it, or real data throws where mock data did not. */
  calibration: CalibrationInfo | CalibrationInfo[];
  citations: Citation[];
  trace_id: string;
  created_at: string;
}

export interface AbstainReason {
  abstain_reason: string;
  what_would_help: Array<{ action: "log_observation" | "more_practice"; dimension: BarsDimension }>;
}

export interface VerifyInput {
  verdict: "confirmed" | "corrected" | "rejected";
  dimension_verdicts: Array<{ dimension: BarsDimension; manager_level: number }>;
  reason: string;
  seconds_to_decide: number;
}

export interface Escalation {
  id: string;
  route: EscalationRoute;
  severity: number;
  rule_id: string;
  summary: string;
}

/** One finished practice run, as My practice lists it. */
export interface PracticeRun {
  id: string;
  scenario_id: string;
  title: string;
  completed_at: string;
  scores: { dimension: BarsDimension; level: number | null }[];
}

export interface VerifyResponse {
  status: "confirmed" | "corrected" | "rejected";
  /**
   * Optional on purpose. The contract promises it and the API now sends it,
   * but an API build that predates that returns only `calibration`, and a
   * required field here made the result panel read `.agreement_rate_before`
   * on undefined and take the page down after a verdict had already been
   * recorded. Declared optional so the compiler forces that case to be
   * handled rather than hidden.
   */
  calibration_updated?: {
    dimension: BarsDimension;
    agreement_rate_before: number;
    agreement_rate_after: number;
    sample_size: number;
    lower?: number | null;
    upper?: number | null;
    state?: CalibrationState;
    advice?: string;
  } | null;
  /** Every dimension, after this verdict. The fallback the panel rebuilds from. */
  calibration?: CalibrationReading[];
  escalation: Escalation | null;
}

// ── Calibration ──────────────────────────────────────────────────────────────

export type CalibrationState =
  | "unmeasured"
  | "provisional"
  | "reliable"
  | "uncertain"
  | "unreliable";

/**
 * Contract `Calibration` (openapi.yaml): one row of the bare-array
 * GET /calibration response. `agreement_rate`/`lower`/`upper` are null until
 * enough verifications exist to present a rate.
 */
export interface CalibrationReading {
  dimension: BarsDimension;
  agreement_rate: number | null;
  lower: number | null;
  upper: number | null;
  sample_size: number;
  state: CalibrationState;
  advice: string;
}

/**
 * Legacy mock shape (computed_at wrapper + Wilson bounds under `wilson_*`
 * names). db.ts/seed.ts still build it; GET /calibration maps it to
 * CalibrationReading[] on the way out. Integration drops this wrapper.
 */
export interface CalibrationDimension {
  dimension: BarsDimension;
  agreement_rate: number;
  /** Integer agreements carried by the seed so ledger rebuilds are exact
   * (agreement_rate × sample_size rounded would drift the first paint). */
  agreements?: number;
  sample_size: number;
  wilson_low: number;
  wilson_high: number;
  /** Contract-aliased fields, optional for gradual migration. */
  lower?: number;
  upper?: number;
  state?: CalibrationState;
  advice?: string;
}

export interface Calibration {
  computed_at: string;
  dimensions: CalibrationDimension[];
}

// ── Insights (Master Doc steps 9–10) ────────────────────────────────────────

export interface TeamPattern {
  id: string;
  classification: Classification;
  staff_count: number;
  dimension: BarsDimension;
  description: string;
  suggested_action: string;
  route: EscalationRoute;
  detected_at: string;
}

export interface TeamInsights {
  window: { start: string; end: string };
  k_threshold: number;
  patterns: TeamPattern[];
  suppressed: Array<{ reason: string; count: number }>;
}
