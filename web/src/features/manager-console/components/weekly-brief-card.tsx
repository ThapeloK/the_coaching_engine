"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Copy,
  Download,
  FileText,
  Loader2,
  Printer,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BriefMarkdown } from "@/components/brief-markdown";
import {
  copyBrief,
  downloadBrief,
  printBrief,
} from "@/lib/brief-export";
import { managerApi } from "@/features/manager-console/api/managerApi";
import type { WeeklyBrief } from "@/lib/types";

/**
 * Turn the patterns on this page into something a GM will actually read, and
 * show it here rather than sending anybody to another website.
 *
 * WHY IT LIVES ON THIS PAGE
 *
 * Team insights ends on a question. A manager can see that ten people share a
 * problem and that the cause is the process rather than the people, and then
 * has to make that case to somebody who was not looking at this screen.
 * Writing that up is half an hour of work and it is the step where the insight
 * usually dies. The button sits directly above the patterns it is written
 * from, so it is next to its own evidence.
 *
 * WHY THE DOCUMENT IS RENDERED HERE
 *
 * The first version handed over a link to manus.im. That works and it is the
 * wrong product: it drops the manager onto a third party page with somebody
 * else's branding, a chat transcript, and a download button, to read a
 * document their own console commissioned. So the console polls for the brief
 * and renders it in place. The link out is gone.
 *
 * The poll is the honest shape of the thing. Manus takes a minute or two, so
 * "still writing" is a normal state, the elapsed seconds are shown so the wait
 * is legible, and the page stays usable throughout: the patterns below are
 * still readable while the agent works.
 *
 * WHAT LEAVES THE BUILDING
 *
 * Only the aggregates already on this screen, each of which has cleared the
 * k-anonymity threshold. No name, no staff id, no transcript. That is stated
 * on the card rather than in a policy document, because the person pressing
 * the button is the one accountable for it.
 */

/** Manus is typically done inside two minutes. Polling every four seconds is
 * often enough to feel live without hammering the API, and the ceiling stops a
 * forgotten tab polling all night. */
const POLL_MS = 4000;
const GIVE_UP_AFTER_MS = 5 * 60 * 1000;

type Phase = "idle" | "commissioning" | "writing" | "ready" | "error";

export function WeeklyBriefCard({ patternCount }: { patternCount: number }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [brief, setBrief] = useState<WeeklyBrief | null>(null);
  const [patternsUsed, setPatternsUsed] = useState<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const [writtenAt, setWrittenAt] = useState<string | undefined>();
  const taskRef = useRef<string | null>(null);
  const timers = useRef<Array<ReturnType<typeof setInterval>>>([]);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearInterval);
    timers.current = [];
  }, []);

  // A tab closed mid-write must not leave intervals running.
  useEffect(() => clearTimers, [clearTimers]);

  // Bring back the last brief this property commissioned.
  //
  // It used to live only in this component's state, so clicking Transfer gap
  // and coming back lost it, and the only way to read it again was to
  // commission another one: a fresh Manus task for a document that already
  // existed. The task id is in the audit trail, so the document is still
  // reachable.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const last = await managerApi.getLatestWeeklyBrief();
        if (cancelled || last.status !== "ready" || !last.markdown) return;
        setBrief(last);
        setWrittenAt(last.commissioned_at);
        setPatternsUsed(last.patterns_included ?? null);
        setPhase("ready");
      } catch {
        // No stored brief is the ordinary state, not an error to show.
      }
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const poll = useCallback(
    (taskId: string) => {
      const startedAt = Date.now();
      const tick = setInterval(() => setSeconds(Math.round((Date.now() - startedAt) / 1000)), 1000);
      const ask = setInterval(async () => {
        if (Date.now() - startedAt > GIVE_UP_AFTER_MS) {
          clearTimers();
          setPhase("error");
          setNote("It is taking longer than expected. Try commissioning it again.");
          return;
        }
        try {
          const next = await managerApi.getWeeklyBrief(taskId);
          if (next.status === "ready") {
            clearTimers();
            setBrief(next);
            setWrittenAt(new Date().toISOString());
            setPhase("ready");
          } else if (next.status === "empty") {
            clearTimers();
            setPhase("error");
            setNote("Manus finished without writing a document. Try again.");
          }
          // "running" just means keep asking.
        } catch {
          // A single failed poll is not a failed brief; the next one may work.
        }
      }, POLL_MS);
      timers.current = [tick, ask];
    },
    [clearTimers],
  );

  const commission = async () => {
    setPhase("commissioning");
    setNote(null);
    setSeconds(0);
    try {
      const response = await managerApi.commissionWeeklyBrief();
      if (response.status === "nothing_to_report") {
        setPhase("error");
        setNote(
          response.detail ??
            "Nothing reached the k-anonymity threshold this period, so there is nothing to write up.",
        );
        return;
      }
      setPatternsUsed(response.patterns_included ?? null);
      if (!response.task_id) {
        setPhase("error");
        setNote("The writing service accepted the job but did not return a handle.");
        return;
      }
      taskRef.current = response.task_id;
      setPhase("writing");
      poll(response.task_id);
    } catch {
      setPhase("error");
      setNote("Could not reach the writing service. The patterns below are unchanged.");
    }
  };

  const restart = () => {
    clearTimers();
    setBrief(null);
    setPhase("idle");
    setNote(null);
  };

  if (patternCount === 0) return null;

  return (
    <div className="fade-up rounded-2xl border bg-card p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <span
            aria-hidden
            className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"
          >
            {phase === "ready" ? (
              <Check className="size-4.5" />
            ) : (
              <FileText className="size-4.5" />
            )}
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-semibold leading-snug">
              {phase === "ready" ? "Brief for the GM" : "Write this up for the GM"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {phase === "ready" ? (
                <>
                  Written from{" "}
                  {patternsUsed === 1
                    ? "one pattern"
                    : `${patternsUsed ?? patternCount} patterns`}{" "}
                  below. Yours to send on.
                </>
              ) : (
                <>
                  A one page operations brief from{" "}
                  {patternCount === 1
                    ? "the pattern below"
                    : `all ${patternCount} patterns below`}
                  : what changed, what it costs to leave alone, and the single
                  action worth taking this week, with the role that owns each
                  one.
                </>
              )}
            </p>
          </div>
        </div>

        {(phase === "idle" || phase === "error") && (
          <Button type="button" onClick={() => void commission()} className="shrink-0">
            <FileText className="size-4" />
            {phase === "error" ? "Try again" : "Commission the brief"}
          </Button>
        )}
        {phase === "ready" && (
          <Button type="button" variant="ghost" onClick={restart} className="shrink-0">
            <RotateCcw className="size-4" />
            Rewrite
          </Button>
        )}
      </div>

      {(phase === "idle" || phase === "error") && (
        <p className="mt-3 flex items-start gap-2 border-t pt-3 text-xs text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-primary" />
          <span>
            Only the patterns above are sent, and every one of them has already
            cleared the k-anonymity threshold. No name, no staff id, no
            transcript.
          </span>
        </p>
      )}

      {note && (
        <p className="mt-3 rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
          {note}
        </p>
      )}

      {(phase === "commissioning" || phase === "writing") && (
        <div className="mt-3 flex items-center gap-3 rounded-xl border bg-muted/30 p-3">
          <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {phase === "commissioning"
                ? "Sending the patterns"
                : "Manus is writing the brief"}
            </p>
            <p className="text-xs text-muted-foreground">
              {phase === "writing"
                ? `${seconds}s. It usually takes a minute or two, and you can keep reading below.`
                : "Only the aggregates above."}
            </p>
          </div>
        </div>
      )}

      {phase === "ready" && brief?.markdown && (
        <div className="mt-3 rounded-xl border bg-background p-4 md:p-5">
          {/* Three exports and no more, because there are only three things a
              duty manager does with this: paste it into an email, attach it,
              or print it. */}
          <div className="mb-4 flex flex-wrap items-center gap-1.5 border-b pb-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => downloadBrief(brief.markdown as string, writtenAt)}
            >
              <Download className="size-3.5" />
              Download
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={async () => {
                const ok = await copyBrief(brief.markdown as string);
                toast[ok ? "success" : "error"](
                  ok
                    ? "Copied. Paste it straight into an email."
                    : "Could not reach the clipboard. Use Download instead.",
                );
              }}
            >
              <Copy className="size-3.5" />
              Copy
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => printBrief(brief.markdown as string, writtenAt)}
            >
              <Printer className="size-3.5" />
              Print or PDF
            </Button>
            <span className="ml-auto text-xs text-muted-foreground">
              Downloads as a document that opens anywhere
            </span>
          </div>

          <BriefMarkdown source={brief.markdown} />

          <p className="mt-4 flex items-start gap-2 border-t pt-3 text-xs text-muted-foreground">
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-primary" />
            <span>
              Written by Manus from {patternsUsed ?? patternCount} k-anonymised
              patterns. No individual was named in what was sent.
              {writtenAt && (
                <> Commissioned {new Date(writtenAt).toLocaleString("en-IE", {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}.</>
              )}
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
