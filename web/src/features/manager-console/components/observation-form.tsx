"use client";

// Talks to the API through http from lib/api/client, never a bare fetch to a
// relative path. A relative "/api/v1/..." resolves against whatever host serves
// the page, so once deployed the browser asks the WEBSITE for coaching data
// instead of the API. This repo also serves routes under /api/v1, so it comes
// back 500 rather than 404 and reads as a backend fault. The client also adds
// the actor header and the idempotency key.

import { useEffect, useMemo, useRef, useState } from "react";
import { Lock, LockOpen, Timer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StaffPicker } from "./staff-picker";
import { BarsLevelPicker } from "@/features/manager-console/components/bars-level-picker";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { dimensionShort, observationDimensionLines } from "@/lib/format";
import type {
  ObservationDimension,
  StaffMember,
  StaffScoreRow,
} from "@/lib/types";

/**
 * The manager's observe surface, redesigned as a one-question-at-a-time
 * wizard with a record anchor: each step asks a single question and slides
 * away when answered (Who → Full/Partial → kind of moment → one dimension at
 * a time → optional note), and the tapped staff member's existing floor
 * observations sit beside it — so the manager sees what is already on the
 * record before their judgement lands.
 *
 * Scope decides what gets shown in the dimension steps: "Full" walks all
 * five BARS dimensions (the moment type's suggested ones first), "Partial"
 * walks only the dimensions that kind of moment usually shows. Anything the
 * manager did not witness — skipped or never asked — stays unrated and is
 * never scored: the ratings array carries ONLY the rated dimensions.
 *
 * Submission keeps the observation route contract: an Idempotency-Key on the
 * write (double tap on hotel wifi cannot log twice), the 409 sequencing gate,
 * and the page's own feedback line instead of a redirect — the manager can
 * keep capturing for the rest of the shift.
 */

const CAPTURE_DIMENSIONS: ObservationDimension[] = [
  "service_recovery",
  "empathy",
  "communication",
  "composure",
  "anticipation",
];

/** Kinds of floor moment offered in the capture; each suggests the BARS
 * dimensions that moment usually scores on. The suggestion orders the
 * dimension steps (first for "Full") and, for "Partial", is the entire list
 * that gets asked at all. */
type MomentKind = "guest_question" | "complaint" | "proactive" | "routine";

const MOMENT_TYPES: ReadonlyArray<{
  id: MomentKind;
  label: string;
  suggest: readonly ObservationDimension[];
}> = [
  {
    id: "guest_question",
    label: "Guest question",
    suggest: ["communication", "anticipation"],
  },
  {
    id: "complaint",
    label: "Complaint or problem",
    suggest: ["service_recovery", "composure"],
  },
  {
    id: "proactive",
    label: "Proactive moment",
    suggest: ["anticipation"],
  },
  {
    id: "routine",
    label: "Routine service",
    suggest: ["communication"],
  },
];

/** "Partial" captures rate only the moment type's suggested dimensions. */
type ScopeKind = "full" | "partial";

/** Wizard position — one question at a time, forward on answer, back via
 * the Back / Change affordances. */
type StepId = "who" | "scope" | "kind" | "dimensions" | "note";

const FLOOR_DOT = "text-[oklch(0.45_0.08_30)]";
const FLOOR_PILL =
  "bg-[oklch(0.66_0.09_30)]/12 text-[oklch(0.45_0.08_30)] border-[oklch(0.66_0.09_30)]/30";

type RecordState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; rows: StaffScoreRow[] };

const CHIP_SELECTED = "border-primary bg-primary text-primary-foreground";
const CHIP_IDLE = "border bg-card text-foreground hover:bg-muted/40";

/** One tap instead of a sentence.
 *
 * Deliberately about what the manager SAW, never about the person: "froze"
 * describes a moment, "is nervous" would be a verdict on somebody, and this
 * text ends up quoted in a coaching recommendation. Short enough to read at a
 * glance and specific enough to be real evidence. */
const NOTE_STARTERS = [
  "Handled it alone, guest left happy",
  "Escalated to me straight away",
  "Froze, did not offer anything",
  "Apologised but took no action",
];

const QUESTION_LABEL = "text-xs font-medium text-muted-foreground";

/** Delay between a BARS row tap and the next dimension sliding in — long
 * enough for the tapped row to register, short enough to stay quick. */
const ADVANCE_MS = 220;

type RatingsState = Partial<Record<ObservationDimension, number>>;

export function ObservationForm({ staff }: { staff: StaffMember[] }) {
  const [staffId, setStaffId] = useState(staff[0]?.id ?? "");
  const [step, setStep] = useState<StepId>("who");
  const [scope, setScope] = useState<ScopeKind | null>(null);
  const [moment, setMoment] = useState<MomentKind | null>(null);
  const [dimIndex, setDimIndex] = useState(0);
  const [ratings, setRatings] = useState<RatingsState>({});
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loggedName, setLoggedName] = useState<string | null>(null);
  const [anchorVersion, setAnchorVersion] = useState(0);
  const [record, setRecord] = useState<RecordState>({ kind: "loading" });
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const member = staff.find((s) => s.id === staffId) ?? staff[0];
  const selectedName = member?.name ?? "";

  // The record anchors follow the tapped chip and refresh after each submit.
  useEffect(() => {
    let cancelled = false;
    setRecord({ kind: "loading" });
    managerApi
      .getScores(staffId, "floor")
      .then((res) => {
        if (cancelled) return;
        const rows = [...res.scores].sort((a, b) =>
          b.recorded_at.localeCompare(a.recorded_at),
        );
        setRecord({ kind: "ready", rows });
      })
      .catch(() => {
        if (!cancelled) setRecord({ kind: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [staffId, anchorVersion]);

  useEffect(
    () => () => {
      if (advanceTimer.current !== null) {
        clearTimeout(advanceTimer.current);
      }
    },
    [],
  );

  const clearAdvanceTimer = () => {
    if (advanceTimer.current !== null) {
      clearTimeout(advanceTimer.current);
      advanceTimer.current = null;
    }
  };

  /** The dimension order for a scope + moment type: the moment type's
   * suggested dimensions first, then (for a full capture) the rest. */
  const dimensionOrder = (
    nextScope: ScopeKind | null,
    nextMoment: MomentKind | null,
  ): ObservationDimension[] => {
    const kind = MOMENT_TYPES.find((m) => m.id === nextMoment);
    if (nextScope === null || kind === undefined) return [];
    const suggested = kind.suggest.filter((d): d is ObservationDimension =>
      CAPTURE_DIMENSIONS.includes(d),
    );
    if (nextScope === "partial") return [...suggested];
    return [
      ...suggested,
      ...CAPTURE_DIMENSIONS.filter((d) => !suggested.includes(d)),
    ];
  };

  const queue = useMemo(() => dimensionOrder(scope, moment), [scope, moment]);

  const clearCapture = () => {
    setScope(null);
    setMoment(null);
    setDimIndex(0);
    setRatings({});
    setNote("");
  };

  /** After Who/scope/moment is answered, land on the first dimension that
   * has no rating yet — or on the note step once every dimension is done. */
  const enterDimensions = (
    nextScope: ScopeKind | null,
    nextMoment: MomentKind | null,
  ) => {
    const nextQueue = dimensionOrder(nextScope, nextMoment);
    if (nextQueue.length === 0) {
      setStep("scope");
      return;
    }
    const firstUnrated = nextQueue.findIndex((d) => ratings[d] === undefined);
    if (firstUnrated === -1) {
      setDimIndex(nextQueue.length - 1);
      setStep("note");
    } else {
      setDimIndex(firstUnrated);
      setStep("dimensions");
    }
  };

  /** Step 1 — Who. A new staff member restarts the capture; re-tapping the
   * current member resumes it at the first question still open. */
  const pickStaff = (id: string) => {
    clearAdvanceTimer();
    setLoggedName(null);
    if (id !== staffId) {
      setStaffId(id);
      clearCapture();
      setStep("scope");
    } else if (scope === null) {
      setStep("scope");
    } else if (moment === null) {
      setStep("kind");
    } else {
      enterDimensions(scope, moment);
    }
  };

  const pickScope = (next: ScopeKind) => {
    clearAdvanceTimer();
    setLoggedName(null);
    if (scope !== next) {
      setScope(next);
      setDimIndex(0);
      setRatings({});
    }
    if (moment === null) {
      setStep("kind");
    } else {
      enterDimensions(next, moment);
    }
  };

  const pickMoment = (next: MomentKind) => {
    clearAdvanceTimer();
    setLoggedName(null);
    if (moment !== next) {
      setMoment(next);
      setDimIndex(0);
      setRatings({});
    }
    enterDimensions(scope, next);
  };

  /** One row tap rates the current dimension AND slides to the next one. */
  const rateDimension = (dimension: ObservationDimension, level: number) => {
    clearAdvanceTimer();
    setLoggedName(null);
    setRatings((prev) => ({ ...prev, [dimension]: level }));
    advanceTimer.current = setTimeout(() => {
      advanceTimer.current = null;
      if (dimIndex + 1 < queue.length) {
        setDimIndex((i) => i + 1);
      } else {
        setDimIndex(queue.length - 1);
        setStep("note");
      }
    }, ADVANCE_MS);
  };

  const skipDimension = () => {
    clearAdvanceTimer();
    setLoggedName(null);
    const current = queue[dimIndex];
    if (current !== undefined && ratings[current] !== undefined) {
      const rest = { ...ratings };
      delete rest[current];
      setRatings(rest);
    }
    if (dimIndex + 1 < queue.length) {
      setDimIndex((i) => i + 1);
    } else {
      setStep("note");
    }
  };

  /** Back walks to the previous question — or the previous dimension when
   * mid-way through the rating steps (pre-filled, so one tap re-confirms). */
  const backStep = () => {
    clearAdvanceTimer();
    if (step === "dimensions") {
      if (dimIndex > 0) {
        setDimIndex((i) => i - 1);
      } else {
        setStep("kind");
      }
    } else if (step === "note") {
      setStep("dimensions");
    } else if (step === "kind") {
      setStep("scope");
    } else if (step === "scope") {
      setStep("who");
    }
  };

  const ratedCount = queue.filter((d) => ratings[d] !== undefined).length;

  const handleSubmit = async () => {
    if (submitting) return;
    if (ratedCount === 0) return;
    const payload = queue
      .filter((d) => ratings[d] !== undefined)
      .map((d) => ({ dimension: d, level: ratings[d] as number }));
    setSubmitting(true);
    try {
      await managerApi.logObservation({
        staff_id: staffId,
        observed_at: new Date().toISOString(),
        context: "Quick floor capture",
        what_happened: note.trim(),
        ratings: payload,
      });
      setLoggedName(selectedName);
      clearCapture();
      setSubmitting(false);
      setStep("scope");
      setAnchorVersion((v) => v + 1);
    } catch {
      toast.error("Could not log the observation. Please retry.");
      setSubmitting(false);
    }
  };

  const currentDimension = queue[dimIndex];

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="rounded-2xl border bg-card p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              Log a floor observation
            </h1>
            <p className="text-sm text-muted-foreground">
              Twenty seconds after the moment, while it&apos;s still yours.
            </p>
          </div>
          <div className="flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
            <Timer className="size-3.5" />
            ~20s
          </div>
        </div>

        <div className="mt-5 space-y-5 border-t pt-5">
          {step !== "who" && (
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <p className={QUESTION_LABEL}>Observing</p>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-2 rounded-lg border border-primary bg-primary px-3 py-1.5 text-primary-foreground">
                  <span className="block text-sm font-semibold leading-tight">
                    {member?.name ?? selectedName}
                  </span>
                  {member && (
                    <span className="block text-xs leading-tight text-primary-foreground/85">
                      {member.role}
                    </span>
                  )}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    clearAdvanceTimer();
                    setStep("who");
                  }}
                >
                  Change
                </Button>
              </div>
            </div>
          )}

          <div key={`${step}:${dimIndex}`} className="msg-in space-y-5">
            {step === "who" && (
              <div className="space-y-2">
                <p className={QUESTION_LABEL}>Who did you observe?</p>
                <StaffPicker
                  staff={staff}
                  selectedId={staffId}
                  onSelect={pickStaff}
                />
              </div>
            )}

            {step === "scope" && (
              <div className="space-y-2">
                <p className={QUESTION_LABEL}>Did you see the whole thing?</p>
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <ScopeButton
                    selected={scope === "full"}
                    onClick={() => pickScope("full")}
                    title="Full"
                    body="I saw the whole moment"
                  />
                  <ScopeButton
                    selected={scope === "partial"}
                    onClick={() => pickScope("partial")}
                    title="Partial"
                    body="I only saw part of it"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Partial rates only the dimensions this kind of moment usually
                  suggests, anything you did not witness stays unrated and is
                  never scored.
                </p>
              </div>
            )}

            {step === "kind" && (
              <div className="space-y-2">
                <p className={QUESTION_LABEL}>What kind of moment was it?</p>
                <div className="flex flex-wrap gap-2">
                  {MOMENT_TYPES.map((m) => {
                    const selected = moment === m.id;
                    return (
                      <button
                        key={m.id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => pickMoment(m.id)}
                        className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                          selected ? CHIP_SELECTED : CHIP_IDLE
                        }`}
                      >
                        {m.label}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  Suggested dimensions are rated first, and are the only ones
                  asked when the sighting was partial.
                </p>
                <p className="flex justify-end">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={backStep}
                  >
                    Back
                  </Button>
                </p>
              </div>
            )}

            {step === "dimensions" && currentDimension !== undefined && (
              <div className="space-y-3">
                <p className={QUESTION_LABEL}>
                  Dimension {dimIndex + 1} of {queue.length}
                </p>
                <div className="space-y-1">
                  <p className="text-lg font-semibold tracking-tight">
                    {observationDimensionLines[currentDimension].name}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {observationDimensionLines[currentDimension].line}
                  </p>
                </div>
                <BarsLevelPicker
                  dimension={currentDimension}
                  value={ratings[currentDimension] ?? null}
                  onChange={(level) => rateDimension(currentDimension, level)}
                  label={observationDimensionLines[currentDimension].name}
                />
                <div className="flex items-center justify-between gap-2 pt-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={backStep}
                  >
                    Back
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={skipDimension}
                  >
                    Skip, doesn&apos;t apply
                  </Button>
                </div>
              </div>
            )}

            {step === "note" && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <p className={QUESTION_LABEL}>What you saw</p>
                  <Input
                    placeholder="One line, in your own words"
                    value={note}
                    onChange={(e) => {
                      setNote(e.target.value);
                      setLoggedName(null);
                    }}
                  />
                  {/* Twenty seconds is the promise on this screen, and nobody
                      types a sentence in twenty seconds walking off a shift.
                      Tapping one fills the line and it stays editable, so the
                      words are still the manager's own. */}
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {NOTE_STARTERS.map((phrase) => (
                      <button
                        key={phrase}
                        type="button"
                        onClick={() => {
                          setNote(phrase);
                          setLoggedName(null);
                        }}
                        className="rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                      >
                        {phrase}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-center gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={backStep}
                    >
                      Back
                    </Button>
                    <Button
                      type="button"
                      size="lg"
                      className="w-full sm:w-auto sm:min-w-64"
                      disabled={submitting || ratedCount === 0 || !note.trim()}
                      onClick={handleSubmit}
                    >
                      {submitting ? "Logging…" : "Log observation"}
                    </Button>
                  </div>
                  {/* Say which requirement is missing. A disabled button with
                      no reason is the same dead end as the error toast this
                      replaces. */}
                  {ratedCount === 0 ? (
                    <p className="text-center text-xs text-muted-foreground">
                      Rate at least one dimension, anything unrated is never
                      scored.
                    </p>
                  ) : !note.trim() ? (
                    <p className="text-center text-xs text-muted-foreground">
                      One line is needed: it is the evidence the coaching read
                      quotes back to you.
                    </p>
                  ) : null}
                </div>
              </div>
            )}
          </div>

          <div className="pt-1">
            {loggedName !== null ? (
              <div
                role="status"
                className="flex items-start justify-center gap-2 rounded-xl border border-primary/25 bg-accent/40 px-4 py-3 text-center"
              >
                <LockOpen className="mt-0.5 size-4 shrink-0 text-primary" />
                <p className="text-sm text-primary">
                  Logged, the transfer-gap read on {loggedName} now lands in
                  the queue. Practice history stays private.
                </p>
              </div>
            ) : (
              <p className="flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
                <Lock className="size-3 shrink-0" />
                Your observation comes first, practice history stays private
                and the coaching read follows your judgement.
              </p>
            )}
          </div>
        </div>
      </div>

      <RecordAnchors name={selectedName} record={record} />
    </div>
  );
}

/** One half of the Full / Partial choice — a big tappable panel, not a chip. */
function ScopeButton({
  selected,
  onClick,
  title,
  body,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  body: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`flex flex-col gap-0.5 rounded-xl border px-4 py-3 text-left transition-colors ${
        selected ? CHIP_SELECTED : CHIP_IDLE
      }`}
    >
      <span className="text-sm font-semibold leading-tight">
        {title}, {body}
      </span>
      {selected && (
        <span className="text-xs text-primary-foreground/85">
          {title === "Full"
            ? "Every dimension gets rated."
            : "Only the dimensions this kind of moment usually shows."}
        </span>
      )}
    </button>
  );
}

/** The tapped staff member's existing floor observations — date, dimension,
 * level — so a manager sees what is already logged before judging again. */
function RecordAnchors({
  name,
  record,
}: {
  name: string;
  record: RecordState;
}) {
  return (
    <aside className="rounded-2xl border bg-card p-4 sm:p-5 lg:sticky lg:top-6">
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className={`size-2 rounded-full bg-current ${FLOOR_DOT}`}
        />
        <p className="text-sm font-semibold">{name}&apos;s floor record</p>
        {record.kind === "ready" && record.rows.length > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">
            {record.rows.length} logged · newest first
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Every rated moment already on the record.
      </p>

      {record.kind === "loading" && (
        <p className="mt-3 text-xs text-muted-foreground">
          Reading {name}&apos;s record…
        </p>
      )}

      {record.kind === "error" && (
        <p className="mt-3 rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
          Could not read the record right now, refresh to retry.
        </p>
      )}

      {record.kind === "ready" && record.rows.length === 0 && (
        <p className="mt-3 rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
          Nothing on the record for {name} yet, your first capture lands here.
        </p>
      )}

      {record.kind === "ready" && record.rows.length > 0 && (
        <ul className="mt-3 space-y-2">
          {record.rows.map((row) => (
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
                    : FLOOR_PILL
                }`}
              >
                {row.level ?? "–"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
