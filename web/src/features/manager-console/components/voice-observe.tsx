"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  CloudOff,
  Loader2,
  Mic,
  Pencil,
  Square,
  Trash2,
  Type,
  Undo2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StaffPicker } from "./staff-picker";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { dimensionShort, observationDimensionLines } from "@/lib/format";
import { useRecorder } from "@/lib/use-recorder";
import {
  definitelyOffline,
  dropRecording,
  listPending,
  queueRecording,
} from "@/lib/pending-audio";
import type {
  ObservationDimension,
  ObservationDraft,
  ObservationDraftResponse,
  StaffMember,
} from "@/lib/types";

/**
 * Say what you saw. Confirm what it heard. Nothing is logged until you do.
 *
 * WHY
 *
 * The tap-through capture is about twenty seconds per person, which is fast for
 * a form and useless for a duty manager with forty staff, because the cost was
 * never the twenty seconds. The cost is stopping. Nobody stops, so the
 * observation never gets logged, so the floor half of the transfer gap stays
 * empty and the product has nothing to compare practice against.
 *
 * Talking does not require stopping. One walk back from the restaurant covers
 * four people, and this turns that into four drafts.
 *
 * THE SHAPE OF THE SCREEN
 *
 * Record, then review. The review is the important half and it gets the space.
 * The manager's own transcript sits at the top with the evidence underlined,
 * and each proposed observation is a card below it. Touching a rating lights
 * up the words that produced it, so the question "why does it say 2" is
 * answered by looking rather than by trusting.
 *
 * Every draft needs one deliberate tap to become real. That is not friction
 * added for its own sake: an observation lands in somebody's record, moves
 * their transfer gap and can send them training. The machine drafts, the
 * manager decides, which is the same rule the coaching side already runs on.
 */

type Phase = "idle" | "typing" | "thinking" | "review";

/** A draft the manager has been editing. Kept separate from what came back so
 * the original is still there to compare against, and so discarding is free. */
interface WorkingDraft extends ObservationDraft {
  key: string;
  staffId: string | null;
  ratings: ObservationDraft["ratings"];
  state: "open" | "saving" | "saved" | "discarded";
  result?: { unlocked: boolean; status: string };
}

const MOMENT_LABELS: Record<ObservationDraft["moment"], string> = {
  guest_question: "Guest question",
  complaint: "Complaint or problem",
  proactive: "Proactive moment",
  routine: "Routine service",
};

/** One hue per dimension, used for the underline in the transcript and the
 * dot on the rating row, so the eye can join them without reading either. */
const DIMENSION_HUE: Record<ObservationDimension, number> = {
  service_recovery: 25,
  empathy: 330,
  communication: 250,
  composure: 195,
  anticipation: 140,
};

function tint(dimension: ObservationDimension, lightness: number, chroma: number) {
  return `oklch(${lightness} ${chroma} ${DIMENSION_HUE[dimension]})`;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : ""))
    .toUpperCase() || "?";
}

/* ------------------------------------------------------------------ capture */

/** The meter. Bars, not a number: nobody reads a number to check a microphone,
 * they look for movement. The centre bars carry more of the level so it reads
 * as a voice rather than a progress bar. */
function LevelMeter({ level, active }: { level: number; active: boolean }) {
  const bars = 9;
  return (
    <div className="flex h-10 items-center justify-center gap-1" aria-hidden>
      {Array.from({ length: bars }, (_, i) => {
        const fromCentre = Math.abs(i - (bars - 1) / 2) / ((bars - 1) / 2);
        const weight = 1 - fromCentre * 0.65;
        const height = active ? 6 + level * 34 * weight : 6;
        return (
          <span
            key={i}
            className="w-1.5 rounded-full bg-primary transition-[height] duration-75 ease-out"
            style={{ height: `${height}px`, opacity: active ? 0.5 + weight * 0.5 : 0.25 }}
          />
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------- transcript */

/** The manager's words, with each piece of evidence underlined in its
 * dimension's colour. The active rating's span is filled in rather than
 * underlined, which is what makes "why does it say 2" a glance. */
function Transcript({
  text,
  spans,
  activeSpan,
}: {
  text: string;
  spans: Array<{ span: [number, number]; dimension: ObservationDimension }>;
  activeSpan: [number, number] | null;
}) {
  const pieces = useMemo(() => {
    const ordered = [...spans].sort((a, b) => a.span[0] - b.span[0]);
    const out: Array<{
      text: string;
      dimension: ObservationDimension | null;
      start: number;
    }> = [];
    let at = 0;
    for (const { span, dimension } of ordered) {
      // Overlapping spans would double-render the same words. The first one
      // wins, which keeps the transcript readable and loses nothing: the
      // rating row still carries its own quote.
      if (span[0] < at) continue;
      if (span[0] > at) {
        out.push({ text: text.slice(at, span[0]), dimension: null, start: at });
      }
      out.push({ text: text.slice(span[0], span[1]), dimension, start: span[0] });
      at = span[1];
    }
    if (at < text.length) {
      out.push({ text: text.slice(at), dimension: null, start: at });
    }
    return out;
  }, [text, spans]);

  return (
    <p className="text-[0.95rem] leading-relaxed text-foreground">
      {pieces.map((piece) => {
        if (!piece.dimension) return <span key={piece.start}>{piece.text}</span>;
        const isActive =
          activeSpan !== null &&
          piece.start >= activeSpan[0] &&
          piece.start < activeSpan[1];
        return (
          <mark
            key={piece.start}
            className="rounded px-0.5 transition-colors duration-150"
            style={{
              backgroundColor: isActive
                ? tint(piece.dimension, 0.88, 0.09)
                : "transparent",
              color: "inherit",
              boxShadow: `inset 0 -2px 0 0 ${tint(piece.dimension, 0.72, 0.12)}`,
            }}
          >
            {piece.text}
          </mark>
        );
      })}
    </p>
  );
}

/* --------------------------------------------------------------- draft card */

function DraftCard({
  draft,
  staff,
  onChange,
  onConfirm,
  onDiscard,
  onHoverSpan,
}: {
  draft: WorkingDraft;
  staff: StaffMember[];
  onChange: (next: WorkingDraft) => void;
  onConfirm: () => void;
  onDiscard: () => void;
  onHoverSpan: (span: [number, number] | null) => void;
}) {
  const [pickingStaff, setPickingStaff] = useState(false);
  const [editingNote, setEditingNote] = useState(false);

  const chosen = staff.find((s) => s.id === draft.staffId);
  const displayName = chosen?.name ?? draft.person.name ?? draft.person.spoken;

  if (draft.state === "discarded") return null;

  if (draft.state === "saved") {
    return (
      <div className="msg-in rounded-2xl border border-primary/30 bg-primary/5 p-4">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <Check className="size-4" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold">Logged for {displayName}</p>
            <p className="text-xs text-muted-foreground">
              {draft.result?.unlocked
                ? "Their practice history is now unlocked to you."
                : "Added to their floor record."}
              {draft.result?.status === "pending_verify" &&
                " A recommendation is waiting in your queue."}
              {draft.result?.status === "abstained" &&
                " The coach abstained: not enough evidence yet."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const setRating = (dimension: ObservationDimension, level: number) => {
    onChange({
      ...draft,
      ratings: draft.ratings.map((r) =>
        r.dimension === dimension ? { ...r, level } : r,
      ),
    });
  };

  const removeRating = (dimension: ObservationDimension) => {
    onChange({
      ...draft,
      ratings: draft.ratings.filter((r) => r.dimension !== dimension),
    });
  };

  const addRating = (dimension: ObservationDimension) => {
    onChange({
      ...draft,
      ratings: [
        ...draft.ratings,
        // Added by hand, so there is no quote to show. The manager is the
        // source here, which is the honest thing for the row to say.
        { dimension, level: 3, quote: "", span: [0, 0] },
      ],
    });
  };

  const unrated = (Object.keys(DIMENSION_HUE) as ObservationDimension[]).filter(
    (d) => !draft.ratings.some((r) => r.dimension === d),
  );

  const ready = draft.staffId !== null && draft.ratings.length > 0;

  return (
    <div className="msg-in space-y-4 rounded-2xl border bg-card p-4 sm:p-5">
      {/* Who. An unmatched or ambiguous name is a question, never a guess. */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            aria-hidden
            className="flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            style={{
              backgroundColor: draft.staffId
                ? "oklch(0.88 0.05 250)"
                : "oklch(0.92 0.03 70)",
              color: draft.staffId ? "oklch(0.38 0.08 250)" : "oklch(0.45 0.06 70)",
            }}
          >
            {draft.staffId ? initials(displayName) : "?"}
          </span>
          <div className="min-w-0">
            <p className="truncate text-base font-semibold leading-tight">
              {draft.staffId ? displayName : `You said "${draft.person.spoken}"`}
            </p>
            <p className="text-xs text-muted-foreground">
              {draft.scope === "full" ? "Saw the whole thing" : "Saw part of it"}
              {" · "}
              {MOMENT_LABELS[draft.moment]}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setPickingStaff((v) => !v)}
        >
          {draft.staffId ? "Change" : "Choose"}
        </Button>
      </div>

      {draft.person.status === "ambiguous" && !draft.staffId && (
        <div className="rounded-xl border border-[oklch(0.76_0.07_74)]/40 bg-[oklch(0.76_0.07_74)]/10 p-3">
          <p className="text-sm font-medium">
            There is more than one {draft.person.spoken}. Which one?
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {(draft.person.candidates ?? []).map((c) => (
              <button
                key={c.staff_id}
                type="button"
                onClick={() => onChange({ ...draft, staffId: c.staff_id })}
                className="inline-flex min-h-10 items-center rounded-xl border bg-card px-3 text-sm font-medium transition-colors hover:border-primary/50 hover:bg-muted/40"
              >
                {c.name}
                {c.department && (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    {c.department.replace(/_/g, " ")}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {draft.person.status === "unmatched" && !draft.staffId && !pickingStaff && (
        <div className="flex items-start gap-2 rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            Nobody on the roster is called {draft.person.spoken}. Choose who you
            meant, or discard this one.
          </span>
        </div>
      )}

      {pickingStaff && (
        <StaffPicker
          staff={staff}
          selectedId={draft.staffId ?? ""}
          onSelect={(id) => {
            onChange({ ...draft, staffId: id });
            setPickingStaff(false);
          }}
        />
      )}

      {/* What happened, in the manager's words, editable because a transcript
          is not always what somebody meant to say. */}
      <div className="rounded-xl bg-muted/40 p-3">
        {editingNote ? (
          <textarea
            autoFocus
            value={draft.what_happened}
            onChange={(e) => onChange({ ...draft, what_happened: e.target.value })}
            onBlur={() => setEditingNote(false)}
            rows={3}
            className="w-full resize-none bg-transparent text-sm outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditingNote(true)}
            className="flex w-full items-start gap-2 text-left text-sm"
          >
            <span className="flex-1">{draft.what_happened || "Add a note"}</span>
            <Pencil className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          </button>
        )}
      </div>

      {/* The ratings. Each row carries the words that produced it. */}
      {draft.needs_rating && draft.ratings.length === 0 && (
        <p className="text-sm text-muted-foreground">
          You mentioned them, but nothing you said pinned to a dimension. Add one
          below if you want this logged.
        </p>
      )}

      <div className="space-y-2.5">
        {draft.ratings.map((rating) => (
          <div
            key={rating.dimension}
            onMouseEnter={() =>
              onHoverSpan(rating.quote ? (rating.span as [number, number]) : null)
            }
            onMouseLeave={() => onHoverSpan(null)}
            className="rounded-xl border p-3 transition-colors hover:bg-muted/30"
          >
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
              <span className="inline-flex items-center gap-2 text-sm font-semibold">
                <span
                  aria-hidden
                  className="size-2.5 rounded-full"
                  style={{ backgroundColor: tint(rating.dimension, 0.72, 0.12) }}
                />
                {dimensionShort[rating.dimension]}
              </span>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((level) => (
                  <button
                    key={level}
                    type="button"
                    aria-label={`${dimensionShort[rating.dimension]} level ${level}`}
                    aria-pressed={rating.level === level}
                    onClick={() => setRating(rating.dimension, level)}
                    className={`inline-flex size-9 items-center justify-center rounded-lg border text-sm font-semibold tabular-nums transition-all duration-150 ${
                      rating.level === level
                        ? "border-transparent text-white shadow-sm"
                        : "bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"
                    }`}
                    style={
                      rating.level === level
                        ? { backgroundColor: tint(rating.dimension, 0.55, 0.13) }
                        : undefined
                    }
                  >
                    {level}
                  </button>
                ))}
                <button
                  type="button"
                  aria-label={`Remove the ${dimensionShort[rating.dimension]} rating`}
                  onClick={() => removeRating(rating.dimension)}
                  className="ml-1 inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              {rating.quote ? (
                <>
                  From your words:{" "}
                  <span
                    className="rounded px-1 py-0.5 font-medium text-foreground"
                    style={{
                      backgroundColor: tint(rating.dimension, 0.92, 0.05),
                    }}
                  >
                    {rating.quote}
                  </span>
                </>
              ) : (
                <>{observationDimensionLines[rating.dimension].line} You added this one.</>
              )}
            </p>
          </div>
        ))}
      </div>

      {unrated.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Also rate</span>
          {unrated.map((dimension) => (
            <button
              key={dimension}
              type="button"
              onClick={() => addRating(dimension)}
              className="inline-flex min-h-8 items-center rounded-lg border border-dashed px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
            >
              + {dimensionShort[dimension]}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 border-t pt-3">
        <Button type="button" variant="ghost" size="sm" onClick={onDiscard}>
          <Trash2 className="mr-1.5 size-3.5" />
          Discard
        </Button>
        <Button
          type="button"
          disabled={!ready || draft.state === "saving"}
          onClick={onConfirm}
        >
          {draft.state === "saving" ? (
            <>
              <Loader2 className="mr-1.5 size-4 animate-spin" />
              Logging
            </>
          ) : (
            <>
              <Check className="mr-1.5 size-4" />
              Log this
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ orchestration */

export function VoiceObserve({ staff }: { staff: StaffMember[] }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [typed, setTyped] = useState("");
  const [transcript, setTranscript] = useState("");
  const [dropped, setDropped] = useState(0);
  const [drafts, setDrafts] = useState<WorkingDraft[]>([]);
  const [activeSpan, setActiveSpan] = useState<[number, number] | null>(null);
  const [queued, setQueued] = useState(0);
  const draftSeq = useRef(0);

  const receive = useCallback((res: ObservationDraftResponse) => {
    if (res.drafts.length === 0) {
      setPhase("idle");
      toast.info(
        res.detail ??
          "Nothing in that pinned to a person and a behaviour. Try naming who you saw and what they did.",
      );
      return;
    }
    setTranscript(res.transcript);
    setDropped(res.dropped_ratings);
    setDrafts(
      res.drafts.map((d) => {
        draftSeq.current += 1;
        return {
          ...d,
          key: `draft-${draftSeq.current}`,
          staffId: d.person.staff_id ?? null,
          state: "open" as const,
        };
      }),
    );
    setPhase("review");
  }, []);

  /* ---- sending, with the offline path folded in ---- */

  const sendAudio = useCallback(
    async (blob: Blob, filename: string) => {
      setPhase("thinking");
      try {
        receive(await managerApi.draftFromVoice(blob, filename));
      } catch {
        // A failed upload is not a lost observation. Keep the audio and try
        // again when the building lets us, because a manager in a service
        // corridor asked to "try again later" simply will not.
        await queueRecording(blob, filename);
        setQueued((n) => n + 1);
        setPhase("idle");
        toast.info(
          definitelyOffline()
            ? "No signal down here. Saved, and it will send itself when you are back."
            : "Could not reach the server. Saved, and it will retry.",
        );
      }
    },
    [receive],
  );

  const recorder = useRecorder({ maxSeconds: 90, onComplete: sendAudio });

  /* ---- the queue drains itself when the signal returns ---- */

  const drain = useCallback(async () => {
    const pending = await listPending();
    if (pending.length === 0) {
      setQueued(0);
      return;
    }
    setQueued(pending.length);
    for (const item of pending) {
      try {
        const res = await managerApi.draftFromVoice(item.blob, item.filename);
        await dropRecording(item.id);
        setQueued((n) => Math.max(0, n - 1));
        // Only surface the first one. Replacing a review the manager is
        // already working through would lose their edits.
        setPhase((current) => {
          if (current === "idle") {
            receive(res);
            return "review";
          }
          return current;
        });
      } catch {
        return; // still no route out; leave the rest queued
      }
    }
  }, [receive]);

  useEffect(() => {
    // Scheduled rather than called straight out of the effect: opening
    // IndexedDB and setting state on the way to the first paint delays the
    // record button for a queue that is almost always empty. The listener is
    // what matters anyway, because the common case is the signal returning
    // while this screen is already open.
    const timer = setTimeout(() => void drain(), 0);
    window.addEventListener("online", drain);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("online", drain);
    };
  }, [drain]);

  const sendTyped = async () => {
    const text = typed.trim();
    if (text.length < 12) {
      toast.info("Say a bit more: who you saw, and what they did.");
      return;
    }
    setPhase("thinking");
    try {
      receive(await managerApi.draftFromText(text));
    } catch {
      setPhase("typing");
      toast.error("Could not read that. Please retry.");
    }
  };

  const confirm = async (draft: WorkingDraft) => {
    if (!draft.staffId) return;
    setDrafts((all) =>
      all.map((d) => (d.key === draft.key ? { ...d, state: "saving" } : d)),
    );
    try {
      const res = await managerApi.logObservation({
        staff_id: draft.staffId,
        observed_at: new Date().toISOString(),
        // The exposure level belongs on the record, not just in the UI: a
        // rating from a glimpse and a rating from the whole interaction are
        // not the same evidence.
        context: `Spoken note. ${
          draft.scope === "full" ? "Saw the whole interaction." : "Saw part of it."
        } ${MOMENT_LABELS[draft.moment]}.`,
        what_happened: draft.what_happened,
        ratings: draft.ratings.map((r) => ({
          dimension: r.dimension,
          level: r.level,
        })),
      });
      setDrafts((all) =>
        all.map((d) =>
          d.key === draft.key
            ? {
                ...d,
                state: "saved",
                result: {
                  unlocked: res.unlocked_practice_history,
                  status: res.recommendation_status,
                },
              }
            : d,
        ),
      );
    } catch {
      setDrafts((all) =>
        all.map((d) => (d.key === draft.key ? { ...d, state: "open" } : d)),
      );
      toast.error("Could not log that one. Please retry.");
    }
  };

  const spans = useMemo(
    () =>
      drafts
        .filter((d) => d.state !== "discarded")
        .flatMap((d) =>
          d.ratings
            .filter((r) => r.quote)
            .map((r) => ({
              span: r.span as [number, number],
              dimension: r.dimension,
            })),
        ),
    [drafts],
  );

  const open = drafts.filter((d) => d.state === "open" || d.state === "saving");
  const saved = drafts.filter((d) => d.state === "saved").length;

  const reset = () => {
    setDrafts([]);
    setTranscript("");
    setTyped("");
    setDropped(0);
    setPhase("idle");
  };

  /* ---------------------------------------------------------------- render */

  if (phase === "review") {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border bg-card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <h2 className="text-sm font-semibold">What you said</h2>
            <Button type="button" variant="ghost" size="sm" onClick={reset}>
              <Undo2 className="mr-1.5 size-3.5" />
              Start again
            </Button>
          </div>
          <div className="mt-3">
            <Transcript text={transcript} spans={spans} activeSpan={activeSpan} />
          </div>
          <p className="mt-3 border-t pt-3 text-xs text-muted-foreground">
            Underlined words are the evidence behind a rating.
            {dropped > 0 && (
              <>
                {" "}
                {dropped === 1 ? "One rating was" : `${dropped} ratings were`}{" "}
                thrown away for quoting words you did not say.
              </>
            )}
          </p>
        </div>

        {open.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {open.length === 1
              ? "One observation to confirm."
              : `${open.length} observations to confirm.`}{" "}
            Nothing is on anyone&apos;s record until you tap Log.
          </p>
        )}

        {drafts.map((draft) => (
          <DraftCard
            key={draft.key}
            draft={draft}
            staff={staff}
            onChange={(next) =>
              setDrafts((all) =>
                all.map((d) => (d.key === next.key ? next : d)),
              )
            }
            onConfirm={() => void confirm(draft)}
            onDiscard={() =>
              setDrafts((all) =>
                all.map((d) =>
                  d.key === draft.key ? { ...d, state: "discarded" } : d,
                ),
              )
            }
            onHoverSpan={setActiveSpan}
          />
        ))}

        {open.length === 0 && (
          <div className="rounded-2xl border border-dashed p-5 text-center">
            <p className="text-sm font-medium">
              {saved > 0
                ? `${saved} logged. That is the floor covered.`
                : "All discarded."}
            </p>
            <Button type="button" className="mt-3" onClick={reset}>
              <Mic className="mr-1.5 size-4" />
              Record another
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-2xl border bg-card p-5 sm:p-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Say what you saw
        </h1>
        <p className="text-sm text-muted-foreground">
          One recording can cover several people. You confirm every one before
          anything is logged.
        </p>
      </div>

      {queued > 0 && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-[oklch(0.76_0.07_74)]/40 bg-[oklch(0.76_0.07_74)]/10 p-3 text-sm">
          <CloudOff className="size-4 shrink-0" />
          <span>
            {queued === 1
              ? "One recording is waiting for signal."
              : `${queued} recordings are waiting for signal.`}{" "}
            They will send themselves.
          </span>
        </div>
      )}

      {phase === "thinking" ? (
        <div className="mt-6 flex flex-col items-center gap-3 py-8">
          <Loader2 className="size-7 animate-spin text-primary" />
          <p className="text-sm font-medium">Reading it back</p>
          <p className="text-xs text-muted-foreground">
            Transcribing, then finding who you named and what you said about them.
          </p>
        </div>
      ) : phase === "typing" ? (
        <div className="mt-5 space-y-3">
          <textarea
            autoFocus
            rows={5}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="Diego handled the checkout dispute. He stayed calm even though the guest was shouting, but he never offered her anything to fix it."
            className="w-full rounded-xl border bg-card p-3 text-sm outline-none transition-colors focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
          />
          <div className="flex items-center justify-between gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setPhase("idle")}
            >
              Back
            </Button>
            <Button type="button" onClick={() => void sendTyped()}>
              Read it back
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-6 flex flex-col items-center gap-4">
          <LevelMeter
            level={recorder.level}
            active={recorder.state === "recording"}
          />

          <button
            type="button"
            onClick={() =>
              recorder.state === "recording" ? recorder.stop() : void recorder.start()
            }
            aria-label={
              recorder.state === "recording" ? "Stop recording" : "Start recording"
            }
            className={`inline-flex size-20 items-center justify-center rounded-full shadow-sm transition-all duration-200 ${
              recorder.state === "recording"
                ? "scale-105 bg-[oklch(0.58_0.18_25)] text-white"
                : "bg-primary text-primary-foreground hover:scale-105"
            }`}
          >
            {recorder.state === "recording" ? (
              <Square className="size-7 fill-current" />
            ) : (
              <Mic className="size-8" />
            )}
          </button>

          <div className="text-center">
            {recorder.state === "recording" ? (
              <p className="text-sm font-medium tabular-nums">
                {recorder.seconds}s
                <span className="text-muted-foreground">
                  {" / "}
                  {recorder.maxSeconds}s
                </span>
              </p>
            ) : recorder.state === "denied" ? (
              <p className="text-sm text-muted-foreground">
                The microphone is blocked. Type it instead.
              </p>
            ) : recorder.state === "unsupported" ? (
              <p className="text-sm text-muted-foreground">
                This browser will not record. Type it instead.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                Tap, then talk. Name who you saw and what they did.
              </p>
            )}
          </div>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setPhase("typing")}
          >
            <Type className="mr-1.5 size-3.5" />
            Type it instead
          </Button>
        </div>
      )}
    </div>
  );
}
