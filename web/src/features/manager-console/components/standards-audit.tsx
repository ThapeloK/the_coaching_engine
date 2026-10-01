"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Copy,
  FileText,
  Loader2,
  ScanSearch,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { http } from "@/lib/api/client";
import { FloorQuestions } from "@/features/manager-console/components/floor-questions";

/** One clause, as the audit resolved it back to the corpus. */
interface Citation {
  ref: string;
  quote: string;
  document: string;
  label: string;
  department: string;
  content: string;
}

interface Finding {
  kind: string;
  title: string;
  explanation: string;
  severity: "high" | "medium" | "low";
  severity_note?: string;
  citations: Citation[];
  missing_sentence?: string;
  impact?: { staff: number; recommendations: number; note: string } | null;
}

interface Report {
  findings: Finding[];
  rejected?: { kind: string; title: string; reasons: string[] }[];
  documents: number;
  document_titles?: string[];
  clauses: number;
  generated_at?: string | null;
}

/** Plain words for each defect. The code uses snake_case; a general manager
 * should never see it. */
const kindLabel: Record<string, string> = {
  contradiction: "Contradiction",
  authority_gap: "Authority gap",
  scope_gap: "Nobody owns this",
  vague_condition: "Untestable rule",
  duplication: "Said twice",
  coverage_hole: "Nothing written",
};

const kindBlurb: Record<string, string> = {
  contradiction: "Two clauses that cannot both be followed.",
  authority_gap: "A decision is required and nothing says who may make it.",
  scope_gap: "One department has a rule, another with the same situation has none.",
  vague_condition: "A trigger no two people would read the same way.",
  duplication: "The same duty in more than one document, which is how they drift.",
  coverage_hole: "A dimension people are scored on with no standard behind it.",
};

const severityTone: Record<string, string> = {
  high: "border-[oklch(0.66_0.09_30)]/40 bg-[oklch(0.66_0.09_30)]/10 text-[oklch(0.45_0.08_30)]",
  medium: "border-[oklch(0.75_0.07_74)]/40 bg-[oklch(0.75_0.07_74)]/12 text-[oklch(0.45_0.07_72)]",
  low: "border-border bg-muted/50 text-muted-foreground",
};

const departmentLabel: Record<string, string> = {
  all: "All departments",
  front_office: "Front office",
  f_and_b: "Food & beverage",
};

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        });
      }}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-muted/60"
    >
      {copied ? <Check className="size-3.5 text-primary" /> : <Copy className="size-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** A quoted clause, shown with where it came from.
 *
 * The quote is rendered inside the full clause rather than on its own, with the
 * quoted part marked, because the whole promise of this screen is that nothing
 * was paraphrased. Showing the sentence it sits in is what lets somebody check
 * that in a glance instead of taking our word for it. */
function Clause({ citation }: { citation: Citation }) {
  const start = citation.content
    .toLowerCase()
    .indexOf(citation.quote.toLowerCase().trim());
  const hasSpan = start >= 0;
  const before = hasSpan ? citation.content.slice(0, start) : "";
  const span = hasSpan
    ? citation.content.slice(start, start + citation.quote.trim().length)
    : citation.content;
  const after = hasSpan
    ? citation.content.slice(start + citation.quote.trim().length)
    : "";

  return (
    <div className="rounded-xl border bg-card/60 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono font-medium">
          {citation.ref}
        </span>
        <span className="font-medium text-foreground">{citation.document}</span>
        <span aria-hidden="true">·</span>
        <span>{citation.label}</span>
        <span className="ml-auto rounded-full border px-2 py-0.5">
          {departmentLabel[citation.department] ?? citation.department}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {before}
        <mark className="rounded bg-primary/15 px-0.5 font-medium text-foreground">
          {span}
        </mark>
        {after}
      </p>
    </div>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  const twoSided = finding.citations.length >= 2;
  return (
    <article className="overflow-hidden rounded-2xl border bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-2.5">
        <span
          className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
            severityTone[finding.severity] ?? severityTone.low
          }`}
        >
          {finding.severity}
        </span>
        <span className="text-xs font-semibold text-foreground">
          {kindLabel[finding.kind] ?? finding.kind}
        </span>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          {kindBlurb[finding.kind]}
        </span>
      </div>

      <div className="space-y-3 p-4">
        <h3 className="text-base font-semibold leading-snug">{finding.title}</h3>
        <p className="text-sm text-muted-foreground">{finding.explanation}</p>

        {finding.severity_note && (
          <p className="flex items-start gap-1.5 text-xs text-[oklch(0.45_0.08_30)]">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
            {finding.severity_note}
          </p>
        )}

        {finding.citations.length > 0 && (
          <div
            className={
              twoSided
                ? "grid gap-2 md:grid-cols-2"
                : "space-y-2"
            }
          >
            {finding.citations.map((citation, i) => (
              <Clause key={`${citation.ref}-${i}`} citation={citation} />
            ))}
          </div>
        )}

        {finding.impact && (
          <div className="flex items-start gap-2 rounded-xl border border-primary/30 bg-primary/5 p-3">
            <ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" />
            <p className="text-sm">
              <span className="font-semibold">Already costing you. </span>
              <span className="text-muted-foreground">{finding.impact.note}</span>
            </p>
          </div>
        )}

        {finding.missing_sentence && (
          <div className="rounded-xl border border-dashed p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                The sentence that isn&apos;t there
              </p>
              <CopyButton text={finding.missing_sentence} />
            </div>
            <p className="mt-2 text-sm italic leading-relaxed">
              &ldquo;{finding.missing_sentence}&rdquo;
            </p>
          </div>
        )}
      </div>
    </article>
  );
}

export function StandardsAudit() {
  const [report, setReport] = useState<Report | null>(null);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    http
      .get<Report>("/standards/audit")
      .then(setReport)
      .catch(() => setReport(null));
  }, []);

  // A visible clock during a forty second wait. Silence for that long reads as
  // a hang, and a manager who thinks it has hung reloads the page and spends
  // the money twice.
  useEffect(() => {
    if (!running) {
      if (timer.current) window.clearInterval(timer.current);
      return;
    }
    setElapsed(0);
    timer.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [running]);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const fresh = await http.post<Report>("/standards/audit", {});
      setReport(fresh);
    } catch {
      setError("The audit could not finish. Nothing was changed.");
    } finally {
      setRunning(false);
    }
  };

  const findings = report?.findings ?? [];
  const high = findings.filter((f) => f.severity === "high").length;

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">
          Your standards, audited
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          An agent reads every clause this property has written and looks for
          the holes that make people hesitate: rules that contradict each other,
          decisions nobody is allowed to make, and situations one department has
          covered and another has not. Every finding quotes the clause it came
          from. Anything it could not quote was thrown away before you saw it.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-4">
        <div className="flex items-center gap-2 text-sm">
          <FileText className="size-4 text-muted-foreground" />
          <span className="font-semibold">{report?.documents ?? 0}</span>
          <span className="text-muted-foreground">documents</span>
          <span className="text-muted-foreground" aria-hidden="true">·</span>
          <span className="font-semibold">{report?.clauses ?? 0}</span>
          <span className="text-muted-foreground">clauses</span>
        </div>

        {findings.length > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground" aria-hidden="true">·</span>
            <span className="font-semibold">{findings.length}</span>
            <span className="text-muted-foreground">findings</span>
            {high > 0 && (
              <span className="rounded-full border border-[oklch(0.66_0.09_30)]/40 bg-[oklch(0.66_0.09_30)]/10 px-2 py-0.5 text-xs font-semibold text-[oklch(0.45_0.08_30)]">
                {high} to fix first
              </span>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {running && (
            <span className="text-xs tabular-nums text-muted-foreground">
              reading {report?.clauses ?? ""} clauses… {elapsed}s
            </span>
          )}
          <Button onClick={run} disabled={running}>
            {running ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Auditing
              </>
            ) : (
              <>
                <ScanSearch className="size-4" />
                {report?.findings?.length ? "Run it again" : "Run the audit"}
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Above the findings: a question is a finding with a name and a
          timestamp on it, and it can be settled in one line. */}
      <FloorQuestions />

      {error && (
        <p className="rounded-xl border border-[oklch(0.66_0.09_30)]/40 bg-[oklch(0.66_0.09_30)]/10 p-3 text-sm text-[oklch(0.45_0.08_30)]">
          {error}
        </p>
      )}

      {!running && findings.length === 0 && (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <ScanSearch className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">No audit has been run yet.</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            It takes about half a minute and costs a few cents. It changes
            nothing: it reads your documents and writes a report.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {findings.map((finding, i) => (
          <FindingCard key={`${finding.kind}-${i}`} finding={finding} />
        ))}
      </div>

      {findings.length > 0 && (
        <footer className="space-y-2 rounded-2xl border bg-muted/30 p-4 text-xs text-muted-foreground">
          <p className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
            <span>
              This edits nothing. It reads the corpus and writes a report; every
              change to a standard is still made by a person, in their own
              document. Findings that could not quote a real clause were
              rejected by the same evidence gate the coaching agent uses
              {report?.rejected?.length
                ? `, which dropped ${report.rejected.length} on this run.`
                : "."}
            </span>
          </p>
          {report?.generated_at && (
            <p className="pl-6">
              Last run {new Date(report.generated_at).toLocaleString()}.
            </p>
          )}
        </footer>
      )}
    </div>
  );
}
