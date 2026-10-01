import { http, isRealApi } from "@/lib/api/client";
import { mockDb } from "@/lib/mock/db";
import type {
  PracticeRun,
  TurnResponse,
  Debrief,
  DebriefRegistration,
  DebriefStatus,
  PracticeAttempt,
  Scenario,
  ScoreResult,
} from "@/lib/types";

/** Staff PWA API — mirrors LLD-B staff endpoints. */

/** Debrief statuses that mean the pipeline has finished (typed debriefs land
 * in exactly one of these: a clause matched, or none did). */
const TERMINAL_STATUSES: ReadonlySet<DebriefStatus> = new Set([
  "extracted",
  "failed",
]);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Mock branch of the debrief flow can return either the legacy
 * `{ id, debrief }` or the frozen `DebriefRegistration` shape while db.ts
 * migrates — both carry the id, and the mock store resolves synchronously,
 * so one follow-up read always finds the parsed debrief. */
type MockCreatedDebrief = {
  id: string;
  debrief?: Debrief;
};

export const staffApi = {
  listScenarios: (): Promise<Scenario[]> =>
    isRealApi() ? http.get("/scenarios") : mockDb.listScenarios(),

  startAttempt: (scenarioId: string): Promise<PracticeAttempt> =>
    isRealApi()
      ? http.post(`/scenarios/${scenarioId}/attempts`, {})
      : mockDb.startAttempt(scenarioId),

  sendTurn: (
    attemptId: string,
    content: string
    // GuestTurn, not an inline shape: it carries the optional audio_id, and
    // spelling it out here silently dropped the guest's voice from the chat.
  ): Promise<TurnResponse> =>
    isRealApi()
      ? http.post(`/attempts/${attemptId}/turns`, { content })
      : mockDb.sendTurn(attemptId, content),

  completeAttempt: (attemptId: string): Promise<ScoreResult> =>
    isRealApi()
      ? http.post(`/attempts/${attemptId}/complete`, {})
      : mockDb.completeAttempt(attemptId),

  getAttempt: (attemptId: string): Promise<PracticeAttempt | undefined> =>
    isRealApi()
      ? http.get(`/attempts/${attemptId}`)
      : mockDb.getAttempt(attemptId),

  /** The signed-in person's own finished runs, newest first.
   *
   * No id argument on purpose: the API reads the actor and will only ever
   * return that person's practice, which is the promise the staff app makes on
   * every screen. The mock has no equivalent, so it answers empty and the
   * caller falls back to its seeded rows. */
  listMyAttempts: (): Promise<PracticeRun[]> =>
    isRealApi() ? http.get("/attempts") : Promise.resolve([]),

  getDebrief: (id: string): Promise<Debrief | undefined> =>
    isRealApi() ? http.get(`/debriefs/${id}`) : mockDb.getDebrief(id),

  /** Speak the debrief instead of typing it.
   *
   * The audio goes to our own Whisper endpoint and is deleted the moment the
   * transcript exists, which is the only version of this we can promise. The
   * mock store has no audio path, so this is real-mode only and the caller
   * falls back to the text field. */
  createDebriefAudio: async (blob: Blob, filename: string): Promise<Debrief> => {
    const registration = await http.upload<DebriefRegistration>(
      "/debriefs/audio",
      blob,
      filename
    );
    // The polled read comes from the database, which has no column for the
    // speaker's original sentence, so what the create response understood is
    // carried across here rather than being lost on the way back.
    const withHeard = (d: Debrief): Debrief =>
      registration.heard ? { ...d, heard: registration.heard } : d;
    const first = await http.get<Debrief>(`/debriefs/${registration.id}`);
    if (TERMINAL_STATUSES.has(first.status)) return withHeard(first);
    await sleep(registration.poll_after_ms);
    const second = await http.get<Debrief>(`/debriefs/${registration.id}`);
    if (TERMINAL_STATUSES.has(second.status)) return withHeard(second);
    throw new Error("Debrief is still processing, check back in a moment.");
  },

  /** POST /debriefs → 202 { id, status, poll_after_ms }, then follow the
   * registration with one GET by id (the frozen polling contract). The mock
   * pipeline resolves inside the POST, so the first read is already terminal
   * there; the real pipeline gets one retry after the advertised cadence. */
  createDebrief: async (text: string): Promise<Debrief> => {
    if (isRealApi()) {
      const registration = await http.post<DebriefRegistration>("/debriefs", {
        text,
      });
      // Same carry-across as the audio path: the polled read comes from the
      // database, which has no column for the speaker's original sentence.
      const withHeard = (d: Debrief): Debrief =>
        registration.heard ? { ...d, heard: registration.heard } : d;
      const firstRead = await http.get<Debrief>(`/debriefs/${registration.id}`);
      if (TERMINAL_STATUSES.has(firstRead.status)) return withHeard(firstRead);
      await sleep(registration.poll_after_ms);
      const secondRead = await http.get<Debrief>(`/debriefs/${registration.id}`);
      if (TERMINAL_STATUSES.has(secondRead.status)) return withHeard(secondRead);
      throw new Error("Debrief is still processing, check back in a moment.");
    }
    const created = (await mockDb.createDebrief(text)) as MockCreatedDebrief;
    if (created.debrief) return created.debrief;
    const stored = await mockDb.getDebrief(created.id);
    if (stored) return stored;
    throw new Error("Debrief could not be read back");
  },
};
