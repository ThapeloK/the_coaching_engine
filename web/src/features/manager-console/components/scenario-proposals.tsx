"use client";

import { useEffect, useState } from "react";
import {
  Check,
  Loader2,
  PenLine,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { http } from "@/lib/api/client";
import { managerApi } from "@/features/manager-console/api/managerApi";

interface Citation {
  ref: string;
  document: string;
  section_path: string;
  content: string;
}

interface Proposal {
  proposal_id: string;
  staff_name: string;
  department: string;
  dimension: string;
  quadrant: "blocked" | "skill_gap" | "recalibrate" | "competent";
  job: string;
  job_why: string;
  practice_mean: number | null;
  floor_mean: number | null;
  gap: number | null;
  title: string;
  situation: string;
  opening_line: string;
  guest_persona: {
    name: string;
    mood: string;
    wants: string;
    concedes_when: string;
  };
  rationale: string;
  audit_findings?: { title: string; kind: string; missing_sentence: string }[];
  citations: Citation[];
  attempts: number;
  proposed_at?: string;
}

const dimensionLabel: Record<string, string> = {
  service_recovery: "Service recovery",
  empathy: "Empathy",
  composure: "Composure",
  communication: "Communication",
  anticipation: "Anticipation",
};

/** The quadrant is the whole argument of this screen, so it gets the strongest
 * visual treatment on the card. "Blocked" is the one worth looking at. */
const quadrantTone: Record<string, string> = {
  blocked:
    "border-[oklch(0.66_0.09_30)]/40 bg-[oklch(0.66_0.09_30)]/10 text-[oklch(0.45_0.08_30)]",
  skill_gap:
    "border-primary/40 bg-primary/10 text-primary",
  recalibrate:
    "border-[oklch(0.75_0.07_74)]/40 bg-[oklch(0.75_0.07_74)]/12 text-[oklch(0.45_0.07_72)]",
  competent: "border-border bg-muted/60 text-muted-foreground",
};

const moodTone: Record<string, string> = {
  annoyed: "bg-[oklch(0.75_0.07_74)]/15 text-[oklch(0.45_0.07_72)]",
  upset: "bg-[oklch(0.66_0.09_30)]/12 text-[oklch(0.45_0.08_30)]",
  neutral: "bg-muted text-muted-foreground",
  calm: "bg-primary/10 text-primary",
};

/** Practice and floor on one line, to scale.
 *
 * A gap is a distance, and two numbers in a sentence do not read as a distance.
 * This is the same idea as the transfer gap page, shrunk to fit on a card, so a
 * manager who has seen one recognises the other. */
function GapBar({
  practice,
  floor,
}: {
  practice: number | null;
  floor: number | null;
}) {
  if (practice === null || floor === null) return null;
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - 1) / 4) * 100));
  const left = Math.min(pct(practice), pct(floor));
  const width = Math.abs(pct(practice) - pct(floor));
  return (
    <div className="min-w-[150px] flex-1">
      <div className="relative h-1.5 rounded-full bg-border">
        <div
          className="absolute h-1.5 rounded-full bg-[oklch(0.75_0.07_74)]/50"
          style={{ left: `${left}%`, width: `${width}%` }}
        />
        <span
          className="absolute -top-1 size-3.5 rounded-full border-2 border-background bg-primary"
          style={{ left: `calc(${pct(practice)}% - 7px)` }}
          title={`Practice ${practice}`}
        />
        <span
          className="absolute -top-1 size-3.5 rounded-full border-2 border-background bg-[oklch(0.55_0.09_30)]"
          style={{ left: `calc(${pct(floor)}% - 7px)` }}
          title={`Floor ${floor}`}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-muted-foreground">
        <span>
          practice <span className="font-semibold text-foreground">{practice}</span>
        </span>
        <span>
          floor <span className="font-semibold text-foreground">{floor}</span>
        </span>
      </div>
    </div>
  );
}

function ProposalCard({
  proposal,
  onSettled,
}: {
  proposal: Proposal;
  onSettled: (id: string) => void;
}) {
  const [busy, setBusy] = useState<"publish" | "discard" | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const act = async (what: "publish" | "discard") => {
    setBusy(what);
    try {
      await http.post(
        `/scenarios/proposals/${proposal.proposal_id}/${what}`,
        what === "discard" ? { reason: "Rejected by manager" } : {}
      );
      setDone(what);
      setTimeout(() => onSettled(proposal.proposal_id), 1200);
    } catch {
      setBusy(null);
    }
  };

  if (done) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border bg-muted/40 p-4 text-sm text-muted-foreground">
        {done === "publish" ? (
          <>
            <Check className="size-4 text-primary" />
            Published to {proposal.staff_name}&apos;s practice list.
          </>
        ) : (
          <>
            <X className="size-4" />
            Discarded, and recorded as a rejection.
          </>
        )}
      </div>
    );
  }

  return (
    <article className="overflow-hidden rounded-2xl border bg-card">
      {/* Who and why, before what. A manager decides on the reason, not the prose. */}
      <div className="space-y-3 border-b bg-muted/25 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{proposal.staff_name}</span>
          <span className="text-xs text-muted-foreground">
            {dimensionLabel[proposal.dimension] ?? proposal.dimension}
          </span>
          <span
            className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
              quadrantTone[proposal.quadrant] ?? quadrantTone.competent
            }`}
          >
            {proposal.quadrant.replace("_", " ")}
          </span>
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs font-semibold text-primary">
            <PenLine className="size-3.5" />
            {proposal.job}
          </span>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <GapBar practice={proposal.practice_mean} floor={proposal.floor_mean} />
          <p className="max-w-xl flex-[2] text-xs text-muted-foreground">
            {proposal.job_why}
          </p>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div>
          <h3 className="text-base font-semibold">{proposal.title}</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {proposal.situation}
          </p>
        </div>

        {/* Rendered the way the staff member will meet it, not as a field in a
            form. A manager approving a scene should see the scene. */}
        <div className="rounded-xl border bg-muted/20 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            How it opens
          </p>
          <div className="flex items-end gap-2">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[oklch(0.92_0.03_82)] text-xs font-bold text-[oklch(0.42_0.045_55)] ring-1 ring-border">
              G
            </div>
            <div className="max-w-[80%]">
              <div className="rounded-2xl rounded-bl-sm border bg-card px-4 py-2.5 text-sm">
                {proposal.opening_line}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="text-muted-foreground">
                  {proposal.guest_persona.name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 font-medium ${
                    moodTone[proposal.guest_persona.mood] ?? moodTone.neutral
                  }`}
                >
                  {proposal.guest_persona.mood}
                </span>
              </div>
            </div>
          </div>
          <dl className="mt-3 grid gap-1.5 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Actually wants</dt>
              <dd>{proposal.guest_persona.wants}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Softens when</dt>
              <dd>{proposal.guest_persona.concedes_when}</dd>
            </div>
          </dl>
        </div>

        <p className="text-sm">
          <span className="font-semibold">Why this one. </span>
          <span className="text-muted-foreground">{proposal.rationale}</span>
        </p>

        {proposal.audit_findings && proposal.audit_findings.length > 0 && (
          <div className="rounded-xl border border-[oklch(0.66_0.09_30)]/30 bg-[oklch(0.66_0.09_30)]/8 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-[oklch(0.45_0.08_30)]">
              <ShieldAlert className="size-3.5" />
              Rehearsing a hole the standards audit already found
            </p>
            <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
              {proposal.audit_findings.map((f, i) => (
                <li key={i}>· {f.title}</li>
              ))}
            </ul>
          </div>
        )}

        {proposal.citations.length > 0 && (
          <details className="rounded-xl border">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
              Grounded in {proposal.citations.length} of this hotel&apos;s own
              clauses
            </summary>
            <div className="space-y-2 border-t p-3">
              {proposal.citations.map((c) => (
                <div key={c.ref} className="text-xs">
                  <p className="font-medium text-foreground">
                    {c.document}
                    <span className="text-muted-foreground">
                      {" · "}
                      {c.section_path.split(">").pop()?.trim()}
                    </span>
                  </p>
                  <p className="mt-0.5 text-muted-foreground">{c.content}</p>
                </div>
              ))}
            </div>
          </details>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <Button onClick={() => act("publish")} disabled={busy !== null}>
            {busy === "publish" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
            Publish to {proposal.staff_name}
          </Button>
          <Button
            variant="outline"
            onClick={() => act("discard")}
            disabled={busy !== null}
          >
            <Trash2 className="size-4" />
            Discard
          </Button>
          <p className="ml-auto text-[11px] text-muted-foreground">
            Nothing reaches {proposal.staff_name} until you publish.
            {proposal.attempts > 1
              ? ` Rewritten once after the gate rejected the first draft.`
              : ""}
          </p>
        </div>
      </div>
    </article>
  );
}

export function ScenarioProposals() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [staff, setStaff] = useState<{ id: string; name: string }[]>([]);
  const [who, setWho] = useState("");
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    http
      .get<Proposal[]>("/scenarios/proposals")
      .then(setProposals)
      .catch(() => setProposals([]));
    managerApi
      .listStaff()
      .then((rows) => {
        const mapped = rows.map((r) => ({ id: r.id, name: r.name }));
        setStaff(mapped);
        setWho((current) => current || mapped[0]?.id || "");
      })
      .catch(() => setStaff([]));
  }, []);

  const write = async () => {
    if (!who) return;
    setWriting(true);
    setError(null);
    try {
      const fresh = await http.post<Proposal>("/scenarios/propose", {
        staff_id: who,
      });
      setProposals((prev) => [fresh, ...prev]);
    } catch {
      setError(
        "Could not write one. The most likely reason is that this person does " +
          "not yet have both a practice and a floor score on any dimension, " +
          "which is a gap we decline to guess at."
      );
    } finally {
      setWriting(false);
    }
  };

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">
          The next scenario
        </h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          The transfer gap says what is wrong with somebody. This writes the
          practice that answers it, grounded in this hotel&apos;s own standards.
          What kind of scenario it writes is decided by the quadrant before any
          model runs, so a person who is blocked is never sent more training.
          Nothing reaches anyone until you publish it.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-4">
        <label htmlFor="who" className="text-sm text-muted-foreground">
          Write one for
        </label>
        <select
          id="who"
          value={who}
          onChange={(e) => setWho(e.target.value)}
          className="min-h-9 rounded-lg border bg-background px-3 text-sm"
        >
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <Button onClick={write} disabled={writing || !who}>
          {writing ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Reading their gap…
            </>
          ) : (
            <>
              <Sparkles className="size-4" />
              Write it
            </>
          )}
        </Button>
        {proposals.length > 0 && (
          <span className="ml-auto text-xs text-muted-foreground">
            {proposals.length} waiting on your read
          </span>
        )}
      </div>

      {error && (
        <p className="rounded-xl border border-[oklch(0.66_0.09_30)]/40 bg-[oklch(0.66_0.09_30)]/10 p-3 text-sm text-[oklch(0.45_0.08_30)]">
          {error}
        </p>
      )}

      {!writing && proposals.length === 0 && (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <Sparkles className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">Nothing proposed yet.</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Pick somebody who has both a practice score and a floor observation,
            and it will read the gap between them.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {proposals.map((p) => (
          <ProposalCard
            key={p.proposal_id}
            proposal={p}
            onSettled={(id) =>
              setProposals((prev) =>
                prev.filter((x) => x.proposal_id !== id)
              )
            }
          />
        ))}
      </div>
    </div>
  );
}
