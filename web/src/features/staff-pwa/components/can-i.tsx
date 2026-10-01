"use client";

import { useEffect, useState } from "react";
import {
  Ban,
  Check,
  CircleHelp,
  Clock,
  Loader2,
  Mic,
  Search,
  Send,
  ShieldQuestion,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVoiceInput } from "@/features/staff-pwa/lib/use-voice-input";
import { http } from "@/lib/api/client";

interface Clause {
  document: string;
  section_path: string;
  content: string;
  department: string;
}

interface Answer {
  question: string;
  department: string;
  verdict: "permits" | "requires_ask" | "prohibits" | "silent";
  plain_answer: string;
  clause: Clause | null;
  near_miss: Clause | null;
  can_ask: boolean;
}

interface Request {
  request_id: string;
  question: string;
  asked_at: string | null;
  answer: {
    verdict: string;
    note: string;
    answered_by: string;
    answered_at: string | null;
  } | null;
}

const departmentLabel: Record<string, string> = {
  all: "all departments",
  front_office: "front office",
  f_and_b: "food & beverage",
};

/** What the staff member reads first, and the only part they may act on.
 *
 * Silence is styled as a finding rather than an error: it is the honest answer,
 * it is very often the correct one in a real hotel, and a staff member who
 * reads "we never wrote this down" should feel informed, not refused. */
const verdictStyle: Record<
  Answer["verdict"],
  { title: string; icon: typeof Check; tone: string; band: string }
> = {
  permits: {
    title: "Yes, you can",
    icon: Check,
    tone: "text-primary",
    band: "border-primary/40 bg-primary/10",
  },
  requires_ask: {
    title: "Yes, but check first",
    icon: Clock,
    tone: "text-[oklch(0.45_0.07_72)]",
    band: "border-[oklch(0.75_0.07_74)]/45 bg-[oklch(0.75_0.07_74)]/12",
  },
  prohibits: {
    title: "No, you can't",
    icon: Ban,
    tone: "text-[oklch(0.45_0.08_30)]",
    band: "border-[oklch(0.66_0.09_30)]/40 bg-[oklch(0.66_0.09_30)]/10",
  },
  silent: {
    title: "Nothing here answers this",
    icon: ShieldQuestion,
    tone: "text-[oklch(0.42_0.06_285)]",
    band: "border-[oklch(0.62_0.09_285)]/40 bg-[oklch(0.62_0.09_285)]/10",
  },
};

/** The questions people actually have at a desk, not feature demos. */
const SUGGESTIONS = [
  "Can I give a waiting guest a coffee?",
  "The guest is furious and I can't fix it. What do I do?",
  "Can I waive a charge they're disputing?",
  "A guest asked about nut allergies. What am I meant to say?",
];

function ClauseCard({ clause, muted }: { clause: Clause; muted?: boolean }) {
  return (
    <div
      className={`rounded-xl border p-3 ${
        muted ? "border-dashed bg-muted/30" : "bg-card"
      }`}
    >
      <p className="text-sm leading-relaxed">{clause.content}</p>
      <p className="mt-2 text-[11px] text-muted-foreground">
        {clause.document}
        {" · "}
        {clause.section_path.split(">").pop()?.trim()}
        {" · "}
        <span className={muted ? "font-semibold text-foreground" : ""}>
          {departmentLabel[clause.department] ?? clause.department}
        </span>
      </p>
    </div>
  );
}

export function CanI() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [requests, setRequests] = useState<Request[]>([]);

  const { listening, toggleVoice, stop } = useVoiceInput({
    demoLine: "Can I give a waiting guest a coffee?",
    onTranscript: setQuestion,
    getBaseInput: () => question,
    enabled: !asking,
    demoNoun: "question",
  });

  useEffect(() => {
    http
      .get<Request[]>("/permissions/requests")
      .then(setRequests)
      .catch(() => setRequests([]));
  }, []);

  const check = async (text?: string) => {
    const q = (text ?? question).trim();
    if (!q || asking) return;
    stop();
    setQuestion(q);
    setAsking(true);
    setAnswer(null);
    setSent(false);
    try {
      setAnswer(await http.post<Answer>("/permissions/ask", { question: q }));
    } catch {
      setAnswer(null);
    } finally {
      setAsking(false);
    }
  };

  const askManager = async () => {
    if (!answer) return;
    setSending(true);
    try {
      await http.post("/permissions/requests", {
        question: answer.question,
        answer,
      });
      setSent(true);
      setRequests(await http.get<Request[]>("/permissions/requests"));
    } catch {
      // Leave the button alone so they can try again.
    } finally {
      setSending(false);
    }
  };

  const style = answer ? verdictStyle[answer.verdict] : null;
  const Icon = style?.icon ?? CircleHelp;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Can I?</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Ask what you&apos;re allowed to do and get the answer from your own
          hotel&apos;s standards. If nobody has written it down, this says so
          instead of guessing, and you can send the question to your manager.
        </p>
      </div>

      <div className="rounded-2xl border bg-card p-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void check();
            }
          }}
          rows={2}
          placeholder={
            listening
              ? "Listening. Ask your question…"
              : "Can I give a waiting guest a coffee?"
          }
          className="w-full resize-none rounded-xl border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
        />
        <div className="mt-2 flex items-center gap-2">
          <Button onClick={() => void check()} disabled={asking || !question.trim()}>
            {asking ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Checking
              </>
            ) : (
              <>
                <Search className="size-4" />
                Check
              </>
            )}
          </Button>
          <Button variant="outline" onClick={toggleVoice} disabled={asking}>
            {listening ? <Square className="size-4" /> : <Mic className="size-4" />}
            {listening ? "Stop" : "Ask out loud"}
          </Button>
        </div>

        {!answer && !asking && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void check(s)}
                className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {answer && style && (
        <div className="space-y-3">
          <div className={`rounded-2xl border p-4 ${style.band}`}>
            <p className={`flex items-center gap-2 font-semibold ${style.tone}`}>
              <Icon className="size-5 shrink-0" />
              {style.title}
            </p>
            {answer.plain_answer && (
              <p className="mt-2 text-sm">{answer.plain_answer}</p>
            )}
            {answer.verdict === "silent" && (
              <p className="mt-2 text-sm">
                Nothing in the{" "}
                {departmentLabel[answer.department] ?? answer.department}{" "}
                standards covers this.{" "}
                <span className="font-medium">That&apos;s not your fault</span>
                {", and "}
                it&apos;s worth someone knowing.
              </p>
            )}
          </div>

          {answer.clause && (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                The rule this comes from
              </p>
              <ClauseCard clause={answer.clause} />
            </div>
          )}

          {answer.near_miss && (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                This exists, but not for your department
              </p>
              <ClauseCard clause={answer.near_miss} muted />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Your colleagues in{" "}
                {departmentLabel[answer.near_miss.department] ??
                  answer.near_miss.department}{" "}
                have this written down. You don&apos;t, so you can&apos;t rely
                on it.
              </p>
            </div>
          )}

          {answer.can_ask && (
            <div className="rounded-2xl border border-dashed p-4">
              {sent ? (
                <p className="flex items-center gap-2 text-sm text-primary">
                  <Check className="size-4" />
                  Sent. You&apos;ll see the answer here, and it stays answered.
                </p>
              ) : (
                <>
                  <p className="text-sm">
                    Send this to your manager and get it settled.
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    They get the question and what the standards said, so they
                    can answer it in one line.
                  </p>
                  <Button
                    className="mt-3"
                    onClick={() => void askManager()}
                    disabled={sending}
                  >
                    {sending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Send className="size-4" />
                    )}
                    Ask my manager
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {requests.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">What you&apos;ve asked</h2>
          <div className="overflow-hidden rounded-2xl border bg-card">
            {requests.map((r, i) => (
              <div key={r.request_id} className={`p-3 ${i > 0 ? "border-t" : ""}`}>
                <p className="text-sm">{r.question}</p>
                {r.answer ? (
                  <div className="mt-2 rounded-xl border border-primary/30 bg-primary/5 p-2.5">
                    <p className="text-xs font-semibold text-primary">
                      {r.answer.verdict === "yes"
                        ? "Yes, you can"
                        : r.answer.verdict === "yes_with_approval"
                          ? "Yes, with approval"
                          : "No"}
                      {r.answer.answered_by ? ` · ${r.answer.answered_by}` : ""}
                    </p>
                    {r.answer.note && (
                      <p className="mt-1 text-sm">{r.answer.note}</p>
                    )}
                  </div>
                ) : (
                  <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Clock className="size-3.5" />
                    Waiting on your manager.
                  </p>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Answers stay here, so you only have to ask once.
          </p>
        </section>
      )}
    </div>
  );
}
