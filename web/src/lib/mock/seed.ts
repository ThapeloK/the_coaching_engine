import type {
  Calibration,
  Debrief,
  GuestTurn,
  Observation,
  PracticeAttempt,
  Recommendation,
  Scenario,
  ScoreResult,
  StaffMember,
} from "@/lib/types";
import { seedStaffMembers } from "./team-staff";

/**
 * Demo seed: the team's generated dataset (staff.json, observations.json,
 * attempts.json, transfer_gaps.json — seed 20260913, snapshot for the
 * 2026-09-13 submission) composed with the narrative exports the demo
 * screens read directly.
 *
 * Composition:
 * - `staffMembers` below is the dataset's 13 front-line staff (staff-001..
 *   staff-013), built by team-staff.ts. Marta (staff-014) is the console
 *   user and Fiona (staff-015) the cross-property L&D admin — neither is a
 *   floor-observation target.
 * - `seedObservations`/`seedAttempts` re-export the 22 real observations
 *   and 45 real practice attempts (team-observations.ts / team-attempts.ts);
 *   mock/db.ts seeds its store from them. Pipeline timestamps import 1:1,
 *   including the 09-06..09-10 dates — real generated data that reads as
 *   history by pitch day.
 * - transfer_gaps.json rows are served verbatim by mock/db.ts's gap,
 *   insights and recommendation derivation (team-gaps.ts).
 * - Diego keeps the legacy id "9f2c-diego" (the roster pickers and
 *   /manager/gap default to it). The staff-001 ↔ 9f2c-diego mapping lives
 *   only in team-staff.ts. `staffPwaActorStaffId` pins the staff-PWA actor
 *   for runtime practice attribution in mock/db.ts.
 * - The narrative objects below (debrief, scenarios, guest scripts, Diego's
 *   practice history and observation, the four recommendations, calibration,
 *   scoring anchor) are display copies the pages import by name. They mirror
 *   the same story the dataset rows carry: diegoScoreResult corresponds to
 *   real attempt att-005 (30 Aug), historyAug29Attempt to att-003 and
 *   historyAug26Attempt to att-002, diegoObservation to obs-001 — each with
 *   its own narrative id, kept out of the mock store.
 */

/** Demo cast: Marta (duty manager) is the console user; Diego is the story arc. */
export const staffMembers: StaffMember[] = seedStaffMembers;

export const currentManager = {
  id: "mgr-marta",
  // staff-014 display_name in seed.sql — the generated roster has no surnames.
  name: "Marta",
  role: "Duty Manager",
  property: "The Liffey Court Hotel, Dublin",
};

// ── Debrief (Diego's 29 Aug room-not-ready shift, already processed) ────────

export const diegoDebrief: Debrief = {
  id: "d3b1-diego",
  status: "extracted",
  transcript:
    "A guest arrived at three o'clock for check-in and the room wasn't ready. I apologised and called the duty manager straight away, I wasn't sure what I was allowed to offer myself.",
  incident: {
    situation_type: "room_not_ready",
    guest_emotion: "frustrated",
    staff_actions: ["apologised", "escalated_to_manager"],
    outcome: "resolved_by_manager",
    dimensions_touched: ["service_recovery", "composure"],
  },
  standard: {
    chunk_id: "chunk-011",
    document: "Complaint Handling, Front Office",
    section_path: "Complaint Handling > Step 6",
    step_number: 6,
    excerpt: "Uncover what resolution the guest actually expects.",
    why_shown:
      "Your account ends at escalation. Step 6 asks you to uncover what the guest actually expects before deciding what to do next.",
  },
  generated_scenario_id: "5e9d-personal",
};

// ── Scenarios ───────────────────────────────────────────────────────────────
// Titles and scored dimensions follow attempts.json verbatim. Each scenario
// keeps its own opener, guest pressure and scoring focus — no shared script.

export const scenarios: Scenario[] = [
  {
    id: "5e9d-personal",
    title: "Room not ready, your 29 August check-in",
    description:
      "Built from your debrief of 29 August. A guest arrives at 3pm after a day of travel and the room is not ready, you froze and escalated instead of recovering.",
    kind: "personal",
    source_debrief_id: "d3b1-diego",
    dimensions: ["service_recovery", "empathy", "composure"],
    duration_minutes: 3,
  },
  {
    id: "s1-starter",
    title: "Room not ready at check-in",
    description:
      "Starter scenario. A guest checks in at 3pm to a room that isn't ready. The front-desk recovery has no documented discretionary limit.",
    kind: "starter",
    source_debrief_id: null,
    dimensions: ["service_recovery", "empathy", "composure"],
    duration_minutes: 3,
  },
  {
    id: "s2-starter",
    title: "Noise complaint at 23:00",
    description:
      "Starter scenario. A guest calls reception at 23:00 about noise from the room above, handled over the phone and at the door, composure first.",
    kind: "starter",
    source_debrief_id: null,
    dimensions: ["empathy", "composure"],
    duration_minutes: 3,
  },
  {
    id: "s3-starter",
    title: "Late main course, wrong order",
    description:
      "Starter scenario (F&B). A six-top has waited forty minutes and the wrong mains arrive. A.L.O.U.D. recovery: apologise, listen, own, understand, deal.",
    kind: "starter",
    source_debrief_id: null,
    dimensions: ["empathy", "service_recovery"],
    duration_minutes: 3,
  },
];

// ── Guest scripts (one per scenario — mock/db.ts never mixes them) ──────────
// db.ts reads the script for the scenario being practised when it opens the
// attempt and when it answers each staff turn. The opener doubles as the
// first guest message of a fresh attempt. The 5e9d-personal opener is the
// same line the seeded in-progress attempt already carries, so resuming the
// replay never shows a different first message.

export interface GuestScript {
  opener: GuestTurn;
  replies: GuestTurn[];
}

export const guestScripts: Record<string, GuestScript> = {
  "5e9d-personal": {
    opener: {
      content:
        "We've been travelling since six this morning. You said the room would be ready at three, it's half past now and you're telling me it isn't. What am I supposed to do?",
      mood: "frustrated",
    },
    replies: [
      {
        content:
          "I've been in airports since five this morning, and you're telling me nobody knows when a room will be free?",
        mood: "escalating",
      },
      {
        content:
          "That's exactly what the young man at check-in told me an hour ago. I want a room, not another promise.",
        mood: "escalating",
      },
      {
        content:
          "Then what can you actually do for us right now? Standing in the lobby is not an answer.",
        mood: "frustrated",
      },
      {
        content:
          "And if the room isn't ready soon we've lost the evening, that has to count for something, surely?",
        mood: "frustrated",
      },
    ],
  },
  "s1-starter": {
    opener: {
      content:
        "Good afternoon. I was told three o'clock, it's gone half past and my room still isn't ready. This is not what I paid for.",
      mood: "frustrated",
    },
    replies: [
      {
        content:
          "I've been travelling since dawn and I'm standing in your lobby with two bags. What exactly is the problem?",
        mood: "escalating",
      },
      {
        content:
          "The clerk at check-in said 'very shortly' half an hour ago. Short-ly. I need a room, not more waiting.",
        mood: "escalating",
      },
      {
        content:
          "So what are you going to do for me right now? I can't stand here all evening.",
        mood: "frustrated",
      },
      {
        content:
          "Fine, but I want to know when, and I don't want to be told 'soon' a third time tonight.",
        mood: "frustrated",
      },
    ],
  },
  "s2-starter": {
    opener: {
      content:
        "It's eleven o'clock and there's a party going on in the room above mine. I need to sleep, I'm up at six.",
      mood: "frustrated",
    },
    replies: [
      {
        content:
          "I already rang down once, forty minutes ago. It's got louder, not quieter.",
        mood: "escalating",
      },
      {
        content:
          "I can hear every word they're saying up there, through the ceiling. This has to stop tonight.",
        mood: "escalating",
      },
      {
        content:
          "So you'll send someone up. When? Because if nothing happens I'm going up there myself, and that won't end well.",
        mood: "frustrated",
      },
      {
        content:
          "Alright, but if it starts again I'm calling back, and I expect it handled properly this time.",
        mood: "frustrated",
      },
    ],
  },
  "s3-starter": {
    opener: {
      content:
        "We've been waiting forty minutes and now the mains are wrong, my wife asked for salmon and this is chicken. At a birthday dinner.",
      mood: "frustrated",
    },
    replies: [
      {
        content:
          "Forty minutes for the wrong food, and you're telling us at the table. Do you know how long we've been here?",
        mood: "escalating",
      },
      {
        content:
          "The children are exhausted, and tables that arrived after us have eaten. This isn't good enough.",
        mood: "escalating",
      },
      {
        content:
          "What are you going to do about it? An apology doesn't feed anyone, and we shouldn't be paying for this.",
        mood: "frustrated",
      },
      {
        content:
          "How long for the correct order? And the coffee you offered had better come off the bill.",
        mood: "frustrated",
      },
    ],
  },
};

// ── Practice: Diego's completed room-not-ready run (30 Aug, real att-005) ───

export const diegoScoreResult: ScoreResult = {
  attempt_id: "8a4e-diego",
  scenario_id: "s1-starter",
  completed_at: "2026-08-30T16:40:00Z",
  scores: [
    { dimension: "service_recovery", level: 4 },
    { dimension: "empathy", level: 4 },
    { dimension: "composure", level: 4 },
    { dimension: "communication", level: null },
    { dimension: "anticipation", level: null },
  ],
  evidence: [
    {
      dimension: "service_recovery",
      quote:
        "I'm sorry your room isn't ready after that journey, let me find out what we can do for you right now, and I'll stay with you until it's sorted.",
      turn_index: 5,
      explains:
        "Resolved + Ownership: apologises with the specific problem, commits to acting now, and adds follow-through. Stops short of an offer, which is the 5.",
    },
    {
      dimension: "empathy",
      quote:
        "You were told three o'clock and it's gone three now, I can hear how frustrating that is after a full day of travel.",
      turn_index: 2,
      explains:
        "Specific Validation: repeats the promise that was broken and names the feeling, without deflecting to housekeeping.",
    },
  ],
  overall_feedback:
    "Strong recovery sequence: acknowledge first, then act. To reach a 5, add a concrete gesture, a lounge seat, a drink, a call-back, once you know what the guest expects.",
};

export const completedAttempt: PracticeAttempt = {
  id: "8a4e-diego",
  scenario_id: "s1-starter",
  status: "completed",
  turns: [],
  result: diegoScoreResult,
};

// ── Earlier practice history (real attempts, same room-not-ready thread) ────

/** 29 Aug 2026 morning run — real att-003, scored 4/4/4 on the same scenario. */
const aug29Result: ScoreResult = {
  attempt_id: "3f7b-aug29",
  scenario_id: "s1-starter",
  completed_at: "2026-08-29T10:40:00Z",
  scores: [
    { dimension: "service_recovery", level: 4 },
    { dimension: "empathy", level: 4 },
    { dimension: "composure", level: 4 },
    { dimension: "communication", level: null },
    { dimension: "anticipation", level: null },
  ],
  evidence: [
    {
      dimension: "empathy",
      quote:
        "You travelled all morning to be told it isn't ready, I'd be fed up too. Let me make this right.",
      turn_index: 3,
      explains:
        "Specific Validation: mirrors what the guest went through and owns the fix, though the concrete offer still comes late.",
    },
  ],
  overall_feedback:
    "You picked up the frustration quickly and stayed composed. Next time, name the concrete next step, where the guest waits, who updates them, in the same breath.",
};

export const historyAug29Attempt: PracticeAttempt = {
  id: "3f7b-aug29",
  scenario_id: "s1-starter",
  status: "completed",
  turns: [],
  result: aug29Result,
};

/** 18 Aug 2026 noise-complaint run — real att-002, empathy/composure only. */
const aug18Result: ScoreResult = {
  attempt_id: "4c8d-aug26",
  scenario_id: "s2-starter",
  completed_at: "2026-08-18T21:05:00Z",
  scores: [
    { dimension: "empathy", level: 4 },
    { dimension: "composure", level: 4 },
    { dimension: "service_recovery", level: null },
    { dimension: "communication", level: null },
    { dimension: "anticipation", level: null },
  ],
  evidence: [
    {
      dimension: "composure",
      quote:
        "I'll come straight up and sort it quietly with the room, I'd rather not discuss it over the phone.",
      turn_index: 4,
      explains:
        "Resolved: keeps calm and moves the conversation to a private channel instead of arguing at the door.",
    },
  ],
  overall_feedback:
    "Your tone stayed steady and you took the conversation out of the corridor. The message to the room itself was brief, a warmer close would lift the empathy score.",
};

export const historyAug26Attempt: PracticeAttempt = {
  id: "4c8d-aug26",
  scenario_id: "s2-starter",
  status: "completed",
  turns: [],
  result: aug18Result,
};

/** Scoring anchor for the personal replay (5e9d-personal). It is the same
 * 29 Aug check-in thread as s1-starter, so it scores on the same calibrated
 * anchors with its own evidence spans — completing the replay in the demo
 * produces a real reading, not the honest-null fallback. */
export const personalScoringAnchor: ScoreResult = {
  attempt_id: "anchor-personal",
  scenario_id: "5e9d-personal",
  completed_at: "2026-08-29T12:10:00Z",
  scores: [
    { dimension: "service_recovery", level: 4 },
    { dimension: "empathy", level: 4 },
    { dimension: "composure", level: 4 },
    { dimension: "communication", level: null },
    { dimension: "anticipation", level: null },
  ],
  evidence: [
    {
      dimension: "empathy",
      quote:
        "Six hours of travel and the room isn't there, I'd be frustrated too. Let me sort this out right now.",
      turn_index: 2,
      explains:
        "Specific Validation: names what the guest went through and takes ownership of the fix.",
    },
    {
      dimension: "service_recovery",
      quote:
        "Here's the plan: I'll take your bags, get you a seat in the lounge, and call you the moment the room is ready.",
      turn_index: 4,
      explains:
        "Resolved + Ownership: a concrete next step the guest can hold on to, without overpromising.",
    },
  ],
  overall_feedback:
    "You named the concrete next step this time, bags, lounge, callback, instead of stopping at the apology. That is the difference from the 29th.",
};

// ── In-progress practice (what Diego opens in the demo — his personal replay)
// Not part of the 45 real attempts — mock/db.ts seeds it alongside them.

export const inProgressAttempt: PracticeAttempt = {
  id: "7b3c-diego",
  scenario_id: "5e9d-personal",
  status: "in_progress",
  turns: [
    {
      turn_index: 1,
      guest: {
        content:
          "We've been travelling since six this morning. You said the room would be ready at three, it's half past now and you're telling me it isn't. What am I supposed to do?",
        mood: "frustrated",
      },
      turns_remaining: 4,
      can_complete: false,
    },
  ],
  result: null,
};

/** Display-only legacy runs the staff history page links to (8a4e-diego,
 * 3f7b-aug29, 4c8d-aug26, 7b3c-diego). db.ts resolves them in getAttempt
 * without storing them, so practice aggregates never double-count. */
export const legacyNarrativeAttempts: PracticeAttempt[] = [
  completedAttempt,
  historyAug29Attempt,
  historyAug26Attempt,
  inProgressAttempt,
];

// ── Observation — what Marta saw at the 29 Aug 3pm check-in ─────────────────
// Display copy of dataset obs-001 (same event, levels 2/3/3). The mock store
// seeds the real obs-001 record; this narrative twin with its own id is what
// the PWA history page reads directly.

export const diegoObservation: Observation = {
  id: "o55c-diego",
  staff_id: "9f2c-diego",
  observed_at: "2026-08-29T15:20:00Z",
  created_at: "2026-08-29T15:20:11Z",
  context: "Guest complaint at front desk, room not ready at 3pm",
  what_happened:
    "Froze, then escalated to me without attempting any recovery.",
  ratings: [
    { dimension: "service_recovery", level: 2 },
    { dimension: "empathy", level: 3 },
    { dimension: "composure", level: 3 },
  ],
};

// ── Recommendations ─────────────────────────────────────────────────────────

/** The star: Diego's policy finding, pending Marta's verify. */
export const diegoRecommendation: Recommendation = {
  id: "r91a-diego",
  status: "pending_verify",
  staff_id: "9f2c-diego",
  classification: "policy",
  headline:
    "This is not a training gap. The front-office standard gives Diego no recovery authority to use.",
  body: "Diego ran the acknowledge-then-offer sequence correctly in practice on both 29 and 30 August. On the floor at 3pm on 29 August he froze and escalated without attempting recovery, and the picture has not moved since. The behaviour he skipped is the one he demonstrably can perform, which points at authority rather than skill: your front-office complaint standard sets no discretionary recovery limit, while the F&B standard does.",
  suggested_action:
    "Set and communicate a discretionary recovery limit for front desk. Do not assign further service recovery practice.",
  calibration: {
    dimension: "service_recovery",
    agreement_rate: 0.84,
    sample_size: 25,
    advice:
      "This system has agreed with your managers 84% of the time on this dimension.",
  },
  citations: [
    {
      kind: "attempt_turn",
      claim: "practice looked confident on service recovery on 30 August",
      source_ref: "attempt:att-005:turn:6",
      quoted_span:
        "I'm sorry your room isn't ready after that journey, let me find out what we can do for you right now, and I'll stay with you until it's sorted.",
    },
    {
      kind: "observation",
      claim: "on the floor on 29 August he froze and escalated without attempting recovery",
      source_ref: "observation:obs-001:what_happened",
      quoted_span:
        "Froze, then escalated to me without attempting any recovery.",
    },
    {
      kind: "sop_chunk",
      claim: "F&B staff have documented discretion to offer; the front-office standard sets none",
      source_ref: "sop:chunk-050",
      quoted_span:
        "Staff may offer a complimentary item (coffee or beverage) at their discretion.",
    },
    {
      kind: "metric",
      claim: "a transfer gap on service recovery, the floor trails practice, held since 29 August",
      source_ref: "metric:gap:service_recovery",
    },
  ],
  trace_id: "01J9Z2K8QW3M",
  created_at: "2026-08-30T17:06:00Z",
};

/** Abstained recommendation — practice-only stream, no floor evidence. */
export const abstainedRecommendation: Recommendation = {
  id: "r7b2-abstain",
  status: "abstained",
  staff_id: "staff-010",
  classification: "behavioural",
  headline: "Not enough evidence yet for grounded coaching.",
  body: "Aoife&apos;s anticipation practice has looked strong, but she has no floor observation yet, a transfer-gap reading needs both streams, so this one is left unscored rather than guessed.",
  suggested_action: "",
  calibration: {
    dimension: "anticipation",
    agreement_rate: 0.75,
    sample_size: 12,
    advice: "Agreement is lower on anticipation than service recovery.",
  },
  citations: [],
  trace_id: "01J9Z2K8QW4N",
  created_at: "2026-09-04T09:05:00Z",
};

/** Behavioural find in the verify queue — Chloe, F&B, communication blocked.
 *  Real numbers: practice 5.0 (att-042) vs floor 3.0 (obs-020), gap 2.0. */
export const chloeRecommendation: Recommendation = {
  id: "r88c-chloe",
  status: "pending_verify",
  staff_id: "staff-012",
  classification: "behavioural",
  headline:
    "Chloe's allergen script is at its strongest in practice; the same care doesn't survive a live wine question.",
  body: "In practice (20 August) she gives the full careful allergen reply, complete with the guest-facing detail. On the floor on 28 August, during a live wine-complaint exchange, the exchange ran shorter and scored 3.0: efficient, but that detail disappeared. The knowledge is there; the floor version needs the same care under pressure.",
  suggested_action:
    "One 5-minute roleplay on the first sentence of a live recommendation, then re-observe next shift.",
  calibration: {
    dimension: "communication",
    agreement_rate: 0.786,
    sample_size: 14,
    advice:
      "Communication has the lowest agreement, treat these readings with care.",
  },
  citations: [
    {
      kind: "attempt_turn",
      claim: "practice looked confident on communication in the 20 August allergen run",
      source_ref: "attempt:att-042:turn:3",
      quoted_span:
        "Of course, let me check the allergen sheet before I place it, and I'll bring it back to you within a minute.",
    },
    {
      kind: "observation",
      claim: "the live wine-question exchange on 28 August scored 3.0",
      source_ref: "observation:obs-020:ratings:communication",
      quoted_span:
        "Listened without interrupting and offered an alternative.",
    },
    {
      kind: "metric",
      claim: "a transfer gap on communication, the floor trails practice",
      source_ref: "metric:gap:communication",
    },
  ],
  trace_id: "01J9Z2K8QW5P",
  created_at: "2026-08-31T09:20:00Z",
};

/** Behavioural find in the verify queue — Bogdan, F&B, communication blocked.
 *  Real numbers: practice 4.0 (att-044) vs floor 3.0 (obs-022), gap 1.0. */
export const bogdanRecommendation: Recommendation = {
  id: "r77e-bogdan",
  status: "pending_verify",
  staff_id: "staff-013",
  classification: "behavioural",
  headline:
    "Bogdan's careful allergen replies shorten when a live guest pushes back.",
  body: "His allergen practice on 19 August is careful and precise. Live on 10 September, a guest unhappy with a wine recommendation got the efficient version and the exchange scored 3.0. The words are in the practice stream; the floor needs the same precision under time pressure.",
  suggested_action:
    "Assign the wine-recommendation starter once with the communication anchors visible, then observe again next shift.",
  calibration: {
    dimension: "communication",
    agreement_rate: 0.786,
    sample_size: 14,
    advice:
      "Communication has the lowest agreement, treat these readings with care.",
  },
  citations: [
    {
      kind: "attempt_turn",
      claim: "practice looked careful on communication in the 19 August allergen run",
      source_ref: "attempt:att-044:turn:2",
      quoted_span:
        "I'll double-check the kitchen on that for you, give me one moment and I'll come back with the answer.",
    },
    {
      kind: "observation",
      claim: "the live wine-question exchange on 10 September scored 3.0",
      source_ref: "observation:obs-022:ratings:communication",
      quoted_span:
        "Listened without interrupting and offered an alternative.",
    },
    {
      kind: "metric",
      claim: "a transfer gap on communication, the floor trails practice",
      source_ref: "metric:gap:communication",
    },
  ],
  trace_id: "01J9Z2K8QW6Q",
  created_at: "2026-09-05T08:40:00Z",
};

export const recommendations: Recommendation[] = [
  diegoRecommendation,
  chloeRecommendation,
  bogdanRecommendation,
  abstainedRecommendation,
];

// ── Calibration (moves visibly on verify — the demo beat) ───────────────────

export const calibration: Calibration = {
  computed_at: "2026-09-05T18:00:00Z",
  dimensions: [
    { dimension: "service_recovery", agreement_rate: 0.84, agreements: 21, sample_size: 25, wilson_low: 0.68, wilson_high: 0.93 },
    { dimension: "empathy", agreement_rate: 0.789, agreements: 15, sample_size: 19, wilson_low: 0.62, wilson_high: 0.92 },
    { dimension: "communication", agreement_rate: 0.786, agreements: 11, sample_size: 14, wilson_low: 0.54, wilson_high: 0.9 },
    { dimension: "composure", agreement_rate: 0.857, agreements: 18, sample_size: 21, wilson_low: 0.7, wilson_high: 0.94 },
    { dimension: "anticipation", agreement_rate: 0.75, agreements: 9, sample_size: 12, wilson_low: 0.46, wilson_high: 0.88 },
  ],
};

// ── Team dataset composition (consumed by mock/db.ts) ───────────────────────
// The store seeds the 22 real observations and 45 real attempts; every other
// dataset surface (transfer gaps, team insights, pending recommendations) is
// derived in mock/db.ts straight from the team-*.ts rows.

/** The staff-PWA's single actor: runtime practice is attributed to this id. */
export const staffPwaActorStaffId = "9f2c-diego";

export { seedStaffMembers } from "./team-staff";
export { seedObservations } from "./team-observations";
export { seedAttempts } from "./team-attempts";
export { TEAM_GAP_ROWS, gapRowsForTeamStaff, findingStaffIds } from "./team-gaps";
