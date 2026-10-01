"use client";

import { useEffect, useState } from "react";
import { Check, Clock, Loader2, MessagesSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { http } from "@/lib/api/client";

interface FloorQuestion {
  request_id: string;
  question: string;
  staff_name: string;
  asked_at: string | null;
  near_miss: { content: string; department: string } | null;
  answer: { verdict: string; note: string; answered_by: string } | null;
}

const verdicts = [
  { key: "yes", label: "Yes" },
  { key: "yes_with_approval", label: "Yes, ask me first" },
  { key: "no", label: "No" },
];

const departmentLabel: Record<string, string> = {
  all: "all departments",
  front_office: "front office",
  f_and_b: "food & beverage",
};

/**
 * Questions people asked mid-shift that their own standards could not answer.
 *
 * This sits above the audit findings on purpose. A finding is a defect we
 * inferred from documents; a question is a person who hit that defect with a
 * guest in front of them, which is the same information with a name and a
 * timestamp on it. Answering one settles it for that person permanently, and
 * several of the same question is a policy somebody needs to write.
 */
export function FloorQuestions() {
  const [questions, setQuestions] = useState<FloorQuestion[]>([]);
  const [note, setNote] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = () =>
    http
      .get<FloorQuestion[]>("/permissions/requests")
      .then(setQuestions)
      .catch(() => setQuestions([]));

  useEffect(() => {
    void load();
  }, []);

  const settle = async (id: string, verdict: string) => {
    setBusy(id);
    try {
      await http.post(`/permissions/requests/${id}/answer`, {
        verdict,
        note: note[id] ?? "",
      });
      await load();
    } finally {
      setBusy(null);
    }
  };

  const open = questions.filter((q) => !q.answer);
  if (!questions.length) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <MessagesSquare className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">Questions from the floor</h2>
        {open.length > 0 && (
          <span className="rounded-full border border-[oklch(0.75_0.07_74)]/45 bg-[oklch(0.75_0.07_74)]/12 px-2 py-0.5 text-xs font-semibold text-[oklch(0.45_0.07_72)]">
            {open.length} waiting
          </span>
        )}
      </div>
      <p className="max-w-3xl text-xs text-muted-foreground">
        Somebody asked this during a shift and their own standards had no
        answer. One line from you settles it for them permanently, and it shows
        up in their app rather than in a corridor.
      </p>

      <div className="space-y-2">
        {questions.map((q) => (
          <article key={q.request_id} className="rounded-2xl border bg-card p-4">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-sm font-semibold">{q.staff_name}</span>
              {q.asked_at && (
                <span className="text-[11px] text-muted-foreground">
                  {new Date(q.asked_at).toLocaleString()}
                </span>
              )}
            </div>
            <p className="mt-1.5 text-sm">{q.question}</p>

            {q.near_miss && (
              <p className="mt-2 rounded-xl border border-dashed bg-muted/30 p-2.5 text-xs text-muted-foreground">
                Written for {departmentLabel[q.near_miss.department] ??
                  q.near_miss.department}
                , not for them: &ldquo;{q.near_miss.content}&rdquo;
              </p>
            )}

            {q.answer ? (
              <div className="mt-3 flex items-start gap-2 rounded-xl border border-primary/30 bg-primary/5 p-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-primary" />
                <p className="text-sm">
                  <span className="font-semibold text-primary">
                    {verdicts.find((v) => v.key === q.answer?.verdict)?.label ??
                      q.answer.verdict}
                  </span>
                  {q.answer.note ? `. ${q.answer.note}` : ""}
                  <span className="text-muted-foreground">
                    {q.answer.answered_by ? ` · ${q.answer.answered_by}` : ""}
                  </span>
                </p>
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                <input
                  value={note[q.request_id] ?? ""}
                  onChange={(e) =>
                    setNote((n) => ({ ...n, [q.request_id]: e.target.value }))
                  }
                  placeholder="One line back to them (optional)"
                  className="min-h-9 w-full rounded-lg border bg-background px-3 text-sm"
                />
                <div className="flex flex-wrap items-center gap-2">
                  {verdicts.map((v) => (
                    <Button
                      key={v.key}
                      size="sm"
                      variant={v.key === "yes" ? "default" : "outline"}
                      disabled={busy === q.request_id}
                      onClick={() => void settle(q.request_id, v.key)}
                    >
                      {busy === q.request_id ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : null}
                      {v.label}
                    </Button>
                  ))}
                  <span className="ml-auto flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Clock className="size-3" />
                    They can see this the moment you answer.
                  </span>
                </div>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
