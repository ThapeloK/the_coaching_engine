"use client";

import { useState } from "react";
import { Check, Loader2, Lock, Play, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { http } from "@/lib/api/client";
import type { GateReport, RlsReport, TraceRun } from "../types";
import { TraceTimeline, Verdict } from "./trace-timeline";

const STAFF = [
  { id: "staff-001", name: "Diego", hint: "blocked, knows it, cannot do it" },
  { id: "staff-002", name: "Niamh", hint: "a genuine skill gap" },
  { id: "staff-013", name: "Bogdan", hint: "scores higher on the floor" },
  { id: "staff-008", name: "Priya", hint: "usually abstains" },
];

/** A row count, where nought is the interesting answer.
 *
 * A plain 0 in a table reads as an empty cell or a bug. It is neither: it is
 * the database refusing, which is the entire claim this panel makes, so it is
 * drawn as a refusal rather than as a small number. */
function RowCount({ label, rows }: { label: string; rows: number }) {
  const denied = rows === 0;
  return (
    <span
      className={`flex min-w-[4.75rem] flex-col items-center rounded-lg px-2.5 py-1.5 ring-1 ${
        denied
          ? "bg-destructive/8 text-destructive ring-destructive/20"
          : "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300"
      }`}
    >
      <span className="inline-flex items-center gap-1 text-base font-semibold leading-none tabular-nums">
        {denied && <Lock className="size-3" aria-hidden />}
        {denied ? "none" : rows}
      </span>
      <span className="mt-0.5 text-[10px] uppercase tracking-wide opacity-80">
        {label}
      </span>
    </span>
  );
}

/** One fact, boxed. Used for the outcome row, where four short facts read
 * better as separate objects than as a sentence joined by middots. */
function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-md bg-background px-2 py-0.5 font-mono text-[11px] text-muted-foreground ring-1 ring-border">
      {children}
    </span>
  );
}

export function GlassBox() {
  const [run, setRun] = useState<TraceRun | null>(null);
  const [gate, setGate] = useState<GateReport | null>(null);
  const [rls, setRls] = useState<RlsReport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go<T>(key: string, fn: () => Promise<T>, set: (v: T) => void) {
    setBusy(key);
    setError(null);
    try {
      set(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      {error ? (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {/* ── 1. where the reasoning lives ─────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            1. &ldquo;It is a wrapper around a language model&rdquo;
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Run the agent on someone and watch every step declare who made it.
            The model drafts and classifies. Code decides what may be said, who
            hears about it, and whether it ships at all.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {STAFF.map((s) => (
              <Button
                key={s.id}
                variant="outline"
                disabled={busy !== null}
                onClick={() =>
                  go(
                    s.id,
                    () => http.post<TraceRun>(`/demo/trace/${s.id}`, {}),
                    setRun
                  )
                }
              >
                {busy === s.id ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Play className="size-3.5" />
                )}
                {busy === s.id ? "Running…" : s.name}
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  {s.hint}
                </span>
              </Button>
            ))}
          </div>

          {run ? (
            <div key={run.staff.id} className="space-y-4">
              <Verdict
                byCode={run.trace.decisions_by_code}
                byModel={run.trace.decisions_by_model}
                ms={run.trace.total_ms}
                tokens={run.trace.total_tokens}
                calls={run.trace.calls.length}
              />

              <TraceTimeline steps={run.trace.steps} />

              {/* The end of the chain, set apart so it reads as the result of
                  the steps above rather than one more step. */}
              <div
                style={{
                  animationDelay: `${run.trace.steps.length * 90 + 120}ms`,
                }}
                className="step-in rounded-xl border bg-muted/30 p-3.5"
              >
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  What shipped
                </p>
                <p className="mt-1.5 text-sm leading-relaxed">
                  {run.outcome.headline ?? run.outcome.abstain_reason}
                </p>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  <Tag>{run.outcome.status}</Tag>
                  {run.outcome.classification && (
                    <Tag>{run.outcome.classification}</Tag>
                  )}
                  {run.outcome.escalation && (
                    <Tag>
                      {run.outcome.escalation.rule_id} →{" "}
                      {run.outcome.escalation.route}
                    </Tag>
                  )}
                  <Tag>
                    {run.outcome.citations}{" "}
                    {run.outcome.citations === 1 ? "citation" : "citations"}
                  </Tag>
                </div>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── 2. the cite gate ─────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            2. &ldquo;It will still make things up&rdquo;
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Five claims go through the gate the live agent uses. One is honest.
            Four are the failure modes that matter, written the way a real model
            failure looks: a confident sentence citing something real and saying
            something it does not say.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            variant="outline"
            disabled={busy !== null}
            onClick={() =>
              go("gate", () => http.get<GateReport>("/demo/gate"), setGate)
            }
          >
            {busy === "gate" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ShieldCheck className="size-3.5" />
            )}
            {busy === "gate" ? "Running…" : "Try to get a lie past it"}
          </Button>

          {gate ? (
            <div className="space-y-2">
              {/* The score first. Five cards of similar height make a reader
                  work out the result; one line states it. */}
              <div className="fade-up flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border bg-muted/30 px-3.5 py-2.5">
                <span className="text-sm">
                  <strong className="tabular-nums text-destructive">
                    {gate.probes.filter((p) => !p.passed).length}
                  </strong>{" "}
                  <span className="text-muted-foreground">
                    fabrications rejected
                  </span>
                </span>
                <span className="text-sm">
                  <strong className="tabular-nums text-emerald-700 dark:text-emerald-300">
                    {gate.probes.filter((p) => p.passed).length}
                  </strong>{" "}
                  <span className="text-muted-foreground">honest claim let through</span>
                </span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {gate.probes.every((p) => p.as_expected)
                    ? "every claim went the way the gate says it should"
                    : "a claim did not behave as expected"}
                </span>
              </div>

              {gate.probes.map((p, i) => (
                <div
                  key={p.id}
                  style={{ animationDelay: `${i * 80}ms` }}
                  className={`step-in overflow-hidden rounded-xl border-l-[3px] bg-card text-sm shadow-sm ${
                    p.passed
                      ? "border-l-emerald-500 ring-1 ring-emerald-500/15"
                      : "border-l-destructive ring-1 ring-destructive/15"
                  }`}
                >
                  <div className="flex items-start gap-2.5 p-3">
                    <span
                      aria-hidden
                      className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full ${
                        p.passed
                          ? "bg-emerald-500/15 text-emerald-600"
                          : "bg-destructive/15 text-destructive"
                      }`}
                    >
                      {p.passed ? (
                        <Check className="size-3.5" />
                      ) : (
                        <X className="size-3.5" />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold leading-snug">{p.title}</p>
                      <p className="mt-1.5 border-l-2 border-muted-foreground/20 pl-2.5 text-xs italic leading-relaxed text-muted-foreground">
                        &ldquo;{p.claim}&rdquo;
                        <span className="not-italic"> cites {p.cited.join(", ")}</span>
                      </p>
                      {p.failures.map((f) => (
                        <p
                          key={f}
                          className="mt-2 inline-flex rounded-md bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive"
                        >
                          {f}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
              <p className="pt-1 text-xs text-muted-foreground">{gate.note} Source:{" "}
                <code className="text-[11px]">{gate.source}</code>.
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── 3. row level security ────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            3. &ldquo;Staff data will leak between roles&rdquo;
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            One question, asked by three people. The SQL never changes: the
            filtering happens inside Postgres, so a bug in our API cannot return
            a row the policy forbids.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            variant="outline"
            disabled={busy !== null}
            onClick={() =>
              go("rls", () => http.get<RlsReport>("/demo/rls"), setRls)
            }
          >
            {busy === "rls" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ShieldCheck className="size-3.5" />
            )}
            {busy === "rls" ? "Running…" : "Ask as three different people"}
          </Button>

          {rls ? (
            <div className="space-y-3">
              {/* Labelled, because the whole argument rests on this being the
                  SAME query every time. Unlabelled it reads as decoration. */}
              <div className="fade-up overflow-hidden rounded-xl border">
                <p className="border-b bg-muted/50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  One query, sent unchanged by all three
                </p>
                <pre className="overflow-x-auto p-3 text-[11px] leading-relaxed">
                  {rls.query}
                </pre>
              </div>

              <div className="space-y-2">
                {rls.viewers.map((v, i) => (
                  <div
                    key={v.viewer}
                    style={{ animationDelay: `${i * 90}ms` }}
                    className="step-in flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border bg-card p-3"
                  >
                    {/* A floor width, because flex-1 alone let this column
                        collapse to one word per line once the counts and the
                        explanation were both on the row. */}
                    <div className="w-full sm:w-auto sm:min-w-[9.5rem] sm:flex-1">
                      <p className="text-sm font-semibold leading-tight">
                        {v.viewer}
                      </p>
                      <p className="text-xs leading-snug text-muted-foreground">
                        {v.who}
                      </p>
                    </div>

                    <div className="flex shrink-0 gap-2">
                      <RowCount label="practice" rows={v.practice_rows} />
                      <RowCount label="floor" rows={v.floor_rows} />
                    </div>

                    <p className="w-full text-xs leading-snug text-muted-foreground sm:w-[16rem] sm:shrink-0">
                      {v.expected}
                    </p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{rls.note}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
