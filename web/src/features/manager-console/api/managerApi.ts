import { http, isRealApi } from "@/lib/api/client";
import { mockDb } from "@/lib/mock/db";
import type {
  CalibrationDimension,
  CalibrationReading,
  CalibrationState,
  Observation,
  ObservationDraftResponse,
  ObservationInput,
  ObservationResponse,
  Recommendation,
  ScoreSource,
  ScoresResponse,
  TeamInsights,
  TransferGap,
  VerifyInput,
  VerifyResponse,
  WeeklyBrief,
  WeeklyBriefResponse,
} from "@/lib/types";

/** Manager Console API — mirrors LLD-B manager/ld endpoints. */

// The mock store (db.ts, owned elsewhere) still serves the legacy
// { computed_at, dimensions } wrapper. Both the /calibration route and this
// client translate it to the frozen bare-array shape on the way out — keep the
// two mappings in step with the thresholds in calibration.py.
const PROVISIONAL_BELOW_N = 10;
const RELIABLE_LOWER_BOUND = 0.75;
const UNRELIABLE_UPPER_BOUND = 0.65;

function stateOf(
  sampleSize: number,
  lower: number,
  upper: number
): CalibrationState {
  if (sampleSize < PROVISIONAL_BELOW_N) return "provisional";
  if (lower >= RELIABLE_LOWER_BOUND) return "reliable";
  if (upper < UNRELIABLE_UPPER_BOUND) return "unreliable";
  return "uncertain";
}

function toCalibrationReading(d: CalibrationDimension): CalibrationReading {
  const lower = d.lower ?? d.wilson_low;
  const upper = d.upper ?? d.wilson_high;
  const state = d.state ?? stateOf(d.sample_size, lower, upper);
  const pct = Math.round((d.agreement_rate ?? 0) * 100);
  const advice =
    d.advice ??
    `Agrees with your managers ${pct}% of the time (${d.sample_size} checks).`;
  return {
    dimension: d.dimension,
    agreement_rate: d.agreement_rate,
    lower,
    upper,
    sample_size: d.sample_size,
    state,
    advice,
  };
}

/** Builds a CalibrationReading[] from the legacy wrapper served by db.ts. */
async function legacyCalibrationToReadings(): Promise<CalibrationReading[]> {
  const legacy = await mockDb.getCalibration();
  return legacy.dimensions.map(toCalibrationReading);
}

export const managerApi = {
  /** The team, from the database in real mode.
   *
   * The overview used to map over the mock seed roster, which fixed the radar
   * at whatever that file happened to contain. A larger property then shows
   * fifteen of its fifty staff and nothing says so. The mock store still
   * answers when the API is off, which is what keeps offline development
   * working. */
  listStaff: async (): Promise<
    Array<{ id: string; name: string; role?: string; department?: string }>
  > => {
    if (!isRealApi()) {
      // The mock store has no roster of its own; the seed file is the roster.
      const { staffMembers } = await import("@/lib/mock/seed");
      return staffMembers;
    }
    // role and department are both on the wire; the old signature hid them,
    // which pushed callers back to the mock seed for a display name.
    const body = await http.get<{
      staff: Array<{
        id: string;
        name: string;
        role: string;
        department?: string;
      }>;
    }>("/staff");
    // Managers and L&D are not coached, so they do not belong on a radar of
    // frontline transfer gaps.
    return body.staff.filter((s) => s.role === "staff");
  },

  listObservations: (): Promise<Observation[]> =>
    isRealApi() ? http.get("/observations") : mockDb.listObservations(),

  logObservation: (input: ObservationInput): Promise<ObservationResponse> =>
    isRealApi()
      ? http.post("/observations", input)
      : mockDb.logObservation(input),

  /**
   * Say what you saw; get drafts back. Writes nothing.
   *
   * The audio goes to our own Whisper endpoint and is dropped the moment it
   * becomes text: no voiceprint is stored, and nothing about HOW it was said
   * is analysed. Mock mode has no extraction, so it returns a fixed example
   * that is obviously an example.
   */
  draftFromVoice: (
    audio: Blob,
    filename: string,
  ): Promise<ObservationDraftResponse> =>
    isRealApi()
      ? http.upload("/observations/voice", audio, filename)
      : Promise.resolve(SAMPLE_DRAFT),

  /** The same extraction from typed text. Also the stage fallback: if
   * transcription stalls in front of judges, the note can be pasted. */
  draftFromText: (text: string): Promise<ObservationDraftResponse> =>
    isRealApi()
      ? http.post("/observations/draft", { text })
      : Promise.resolve(SAMPLE_DRAFT),

  getGap: (staffId: string): Promise<TransferGap | undefined> =>
    isRealApi()
      ? http.get(`/staff/${staffId}/gap`)
      : mockDb.getGap(staffId),

  listRecommendations: (): Promise<Recommendation[]> =>
    isRealApi()
      ? http.get("/recommendations")
      : mockDb.listRecommendations(),

  getRecommendation: (id: string): Promise<Recommendation | undefined> =>
    isRealApi()
      ? http.get(`/recommendations/${id}`)
      : mockDb.getRecommendation(id),

  verifyRecommendation: (
    id: string,
    input: VerifyInput
  ): Promise<VerifyResponse> =>
    isRealApi()
      ? http.post(`/recommendations/${id}/verify`, input)
      : mockDb.verifyRecommendation(id, input),

  /** GET /calibration → bare array of CalibrationReading (frozen contract).
   * The route handler is the canonical shape; in mock mode the legacy wrapper
   * from db.ts is mapped here so server pages see the frozen shape too. */
  getCalibration: (): Promise<CalibrationReading[]> =>
    isRealApi()
      ? http.get("/calibration")
      : legacyCalibrationToReadings(),

  /** GET /staff/{id}/scores?source=practice|floor — reads a staff member's
   * two evidence streams. Call from client components (or real-mode servers):
   * the scores route handler is the single implementation for both modes and
   * answers 409 (problem+json) for practice before the manager's first floor
   * observation of that person exists. */
  getScores: (
    staffId: string,
    source: ScoreSource
  ): Promise<ScoresResponse> =>
    http.get(`/staff/${staffId}/scores?source=${source}`),

  /**
   * Hand this period's cohort patterns to Manus to be written up.
   *
   * Only the k-anonymised aggregates already on screen leave the building:
   * the prompt is assembled from the same team_insights() this page renders,
   * so nothing reaches an external agent that the manager cannot already see,
   * and no individual is named. Mock mode does not call out at all.
   */
  commissionWeeklyBrief: (): Promise<WeeklyBriefResponse> =>
    isRealApi()
      ? http.post("/reports/weekly", {})
      : Promise.resolve({
          status: "nothing_to_report",
          detail: "Mock mode does not commission real briefs.",
        }),

  /** The brief this property last commissioned, so it survives navigation.
   *
   * Reads the Manus task id back out of the audit trail, which already records
   * every commission, and re-fetches the document. Without it the brief lived
   * in one component's state and clicking any other tab threw it away. */
  getLatestWeeklyBrief: (): Promise<WeeklyBrief> =>
    isRealApi()
      ? http.get("/reports/weekly/latest")
      : Promise.resolve({ status: "none" as const }),

  /** What Manus wrote, so the manager never leaves the console to read a
   * document the console commissioned. Returns "running" until it is done. */
  getWeeklyBrief: (taskId: string): Promise<WeeklyBrief> =>
    isRealApi()
      ? http.get(`/reports/weekly/${taskId}`)
      : Promise.resolve({ status: "empty" as const }),

  getTeamInsights: (): Promise<TeamInsights> =>
    isRealApi()
      ? http.get("/insights/team")
      : mockDb.getTeamInsights(),
};

/** Mock-mode stand-in. Static on purpose: a second extractor implemented here
 * would drift away from the real one and quietly lie about what it does. */
const SAMPLE_DRAFT: ObservationDraftResponse = {
  transcript:
    "Diego just handled that checkout dispute. He stayed completely calm even " +
    "though the guest was shouting at him, but he never actually offered her " +
    "anything to fix it.",
  drafts: [
    {
      person: { status: "matched", spoken: "Diego", staff_id: "staff-001", name: "Diego Ramos" },
      moment: "complaint",
      scope: "full",
      what_happened: "He stayed calm while the guest was shouting, but offered nothing to fix it.",
      ratings: [
        { dimension: "composure", level: 4, quote: "stayed completely calm", span: [36, 58] },
        {
          dimension: "service_recovery",
          level: 2,
          quote: "never actually offered her anything to fix it",
          span: [104, 148],
        },
      ],
      needs_rating: false,
    },
  ],
  dropped_ratings: 0,
};
