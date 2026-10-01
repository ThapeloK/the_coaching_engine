"use client";

import { Database, Cpu, Sparkles } from "lucide-react";
import type { StepActor, TraceStep } from "../types";

/**
 * The agent's run, drawn as the chain it is rather than the log it was.
 *
 * WHAT THIS PANEL HAS TO WIN
 *
 * One argument: "it is a wrapper around a language model". The evidence is
 * already in the data, because every step declares who made it, but the old
 * rendering buried it. Seven near-identical rows with a small word on the left
 * made the reader do the counting, and a judge three metres from a screen will
 * not count.
 *
 * So the colour does the counting. Each step hangs off a spine, and the spine
 * is the colour of whoever decided that step. A run where one dot in seven is
 * violet makes the case before anybody reads a word, and it is not a claim we
 * made: it is the shape of the trace.
 *
 * WHY THE STEPS ARRIVE ONE AT A TIME
 *
 * The other thing a judge suspects is that this is canned. Watching the chain
 * assemble, in the order the agent ran, answers that better than a sentence
 * insisting it is live. The delay is per step and short: this is a reveal, not
 * a loading screen, and the whole thing is complete in about a second.
 *
 * WHY THE MODEL STEP IS DRAWN LOUDER
 *
 * It is the only place judgement happens, and it is the step people expect to
 * be everywhere. Making it unmissable is the honest move, not the defensive
 * one: here is exactly where the model was allowed to decide something, and
 * here is the step immediately before it where code took options off the table.
 */

const ACTOR: Record<
  StepActor,
  {
    label: string;
    icon: typeof Database;
    dot: string;
    spine: string;
    chip: string;
    ring: string;
  }
> = {
  database: {
    label: "database",
    icon: Database,
    dot: "bg-sky-500",
    spine: "bg-sky-500/25",
    chip: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
    ring: "ring-sky-500/20",
  },
  code: {
    label: "code",
    icon: Cpu,
    dot: "bg-emerald-500",
    spine: "bg-emerald-500/25",
    chip: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    ring: "ring-emerald-500/20",
  },
  model: {
    label: "model",
    icon: Sparkles,
    dot: "bg-violet-500",
    spine: "bg-violet-500/30",
    chip: "bg-violet-500/12 text-violet-700 dark:text-violet-300",
    ring: "ring-violet-500/25",
  },
};

/** Values a person can read at a glance, instead of one long comma run.
 *
 * The worst offender was the per-dimension readout, which arrived as
 * "service_recovery · 3.17 · blocked, empathy · 0.7 · blocked, ..." and is the
 * single most interesting line in the trace. It is now one chip per dimension
 * with the number given room. */
function DetailValue({ label, value }: { label: string; value: unknown }) {
  const pretty = label.replace(/_/g, " ");

  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return (
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {pretty}
        </span>
        <span className="flex flex-wrap gap-1.5">
          {value.map((item, i) => {
            const text =
              typeof item === "object" && item !== null
                ? Object.values(item as Record<string, unknown>).join(" · ")
                : String(item);
            return (
              <span
                key={`${text}-${i}`}
                className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] leading-relaxed text-foreground/80"
              >
                {text}
              </span>
            );
          })}
        </span>
      </div>
    );
  }

  if (typeof value === "object") return null;

  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {pretty}
      </span>
      <span className="font-mono text-[12px] text-foreground/85">
        {String(value)}
      </span>
    </div>
  );
}

function Step({ step, index }: { step: TraceStep; index: number }) {
  const actor = ACTOR[step.actor];
  const Icon = actor.icon;
  const isModel = step.actor === "model";
  const note = typeof step.detail.note === "string" ? step.detail.note : null;
  const fields = Object.entries(step.detail).filter(
    ([key, value]) => key !== "note" && key !== "decisive" && value != null,
  );

  // 90ms apart: fast enough that nobody is waiting, slow enough that the eye
  // reads it as a sequence rather than a flash.
  const delay = `${index * 90}ms`;

  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {/* The spine, coloured by whoever made this step. */}
      <span
        aria-hidden
        className={`absolute left-[11px] top-6 bottom-0 w-px ${actor.spine} last:hidden`}
      />
      <span
        aria-hidden
        style={{ animationDelay: `calc(${delay} + 120ms)` }}
        className={`dot-in relative z-10 mt-1 flex size-[23px] shrink-0 items-center justify-center rounded-full ring-4 ring-background ${actor.dot}`}
      >
        <Icon className="size-3 text-white" />
      </span>

      <div
        style={{ animationDelay: delay }}
        className={`step-in min-w-0 flex-1 rounded-xl px-3 py-2 transition-colors ${
          isModel ? `bg-violet-500/[0.06] ring-1 ${actor.ring}` : ""
        }`}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${actor.chip}`}
          >
            {actor.label}
          </span>
          <p className="text-sm font-semibold leading-snug">{step.label}</p>
          {step.ms > 0 && (
            <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground">
              {step.ms}ms
            </span>
          )}
        </div>

        {fields.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {fields.map(([key, value]) => (
              <DetailValue key={key} label={key} value={value} />
            ))}
          </div>
        )}

        {note && (
          <p className="mt-2 border-l-2 border-muted-foreground/20 pl-2.5 text-xs italic leading-relaxed text-muted-foreground">
            {note}
          </p>
        )}
      </div>
    </li>
  );
}

/**
 * The headline, sized like the argument it is.
 *
 * This number was previously a line of small text among three others. It is
 * the whole panel: how many of the decisions in a run were taken by code that
 * can be read, versus by a model that cannot be cross-examined.
 */
export function Verdict({
  byCode,
  byModel,
  ms,
  tokens,
  calls,
}: {
  byCode: number;
  byModel: number;
  ms: number;
  tokens: number;
  calls: number;
}) {
  const total = Math.max(1, byCode + byModel);
  const share = Math.round((byCode / total) * 100);

  return (
    <div className="fade-up rounded-2xl border bg-gradient-to-br from-emerald-500/[0.07] to-violet-500/[0.07] p-4">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex items-end gap-5">
          <div>
            <p className="text-3xl font-semibold leading-none tabular-nums text-emerald-700 dark:text-emerald-300">
              {byCode}
            </p>
            <p className="mt-1 text-xs font-medium text-muted-foreground">
              decisions by code
            </p>
          </div>
          <div>
            <p className="text-3xl font-semibold leading-none tabular-nums text-violet-700 dark:text-violet-300">
              {byModel}
            </p>
            <p className="mt-1 text-xs font-medium text-muted-foreground">
              by the model
            </p>
          </div>
        </div>
        <p className="font-mono text-[11px] text-muted-foreground">
          {ms}ms · {tokens} tokens · {calls} model{" "}
          {calls === 1 ? "call" : "calls"}
        </p>
      </div>

      {/* One bar, two colours, no legend needed: the colours are the same ones
          the steps below use. */}
      <div
        className="mt-3 flex h-2 overflow-hidden rounded-full bg-violet-500/30"
        role="img"
        aria-label={`${share}% of decisions were taken by code`}
      >
        <div
          className="h-full rounded-l-full bg-emerald-500/80 transition-[width] duration-700 ease-out"
          style={{ width: `${share}%` }}
        />
      </div>
    </div>
  );
}

export function TraceTimeline({ steps }: { steps: TraceStep[] }) {
  return (
    <ol className="relative">
      {steps.map((step, i) => (
        <Step key={step.seq} step={step} index={i} />
      ))}
    </ol>
  );
}
