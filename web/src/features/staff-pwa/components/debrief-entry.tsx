"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Captions,
  Languages,
  Mic,
  Sparkles,
  Square,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { staffApi } from "@/features/staff-pwa/api/staffApi";
import { useVoiceInput } from "@/features/staff-pwa/lib/use-voice-input";
import { useRecorder } from "@/lib/use-recorder";
import { isRealApi } from "@/lib/api/client";
import type { Debrief } from "@/lib/types";

const DEMO_VOICE_LINE =
  "A guest asked for a late checkout and I wasn't sure if I could say yes, so I checked the duty manager's guidance.";


/** "dominican_republic" is a database key. People are from the Dominican
 * Republic. */
function prettyCountry(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function DebriefEntry() {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Debrief | null>(null);

  // Speaking it is the real path: the people this is built for are finishing a
  // shift on their feet and will not type three paragraphs into a phone. The
  // text box stays for anyone who would rather write, or whose browser will
  // not give us a microphone.
  const handleRecorded = async (blob: Blob, filename: string) => {
    setSubmitting(true);
    try {
      const debrief = await staffApi.createDebriefAudio(blob, filename);
      if (debrief.status === "failed") {
        toast.error("That was too short to work with, try a sentence or two more.");
        return;
      }
      setResult(debrief);
      if (debrief.transcript) setText(debrief.transcript);
      toast.success("Got it. Here's what your standard says");
    } catch {
      toast.error("Could not send that recording. You can type it instead.");
    } finally {
      setSubmitting(false);
    }
  };

  const recorder = useRecorder({ onComplete: handleRecorded });
  const recording = recorder.state === "recording";

  const { listening, toggleVoice, stop } = useVoiceInput({
    demoLine: DEMO_VOICE_LINE,
    onTranscript: setText,
    getBaseInput: () => text,
    enabled: !submitting,
    demoNoun: "debrief",
  });

  const handleSubmit = async () => {
    if (submitting) return;
    if (!text.trim()) {
      toast.warning("Tell us what happened first, a sentence is enough.");
      return;
    }
    stop();
    setSubmitting(true);
    try {
      // POST registers the debrief (202) and the follow-up read returns the
      // cited standard. The mock resolves instantly, so there is no polling
      // spinner to jitter the UI — the read below is already the result.
      const debrief = await staffApi.createDebrief(text);
      if (debrief.status === "failed") {
        toast.error(
          "Could not match that to a standard yet. Try one more sentence about what happened."
        );
        return;
      }
      setResult(debrief);
      toast.success("Got it. Here's what your standard says");
    } catch {
      toast.error("Could not save that. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (result?.standard) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border bg-card p-4">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-full bg-[oklch(0.66_0.055_152)]/15">
              <Sparkles className="size-4 text-[oklch(0.38_0.055_152)]" />
            </div>
            <p className="text-sm font-semibold">
              Your hotel&apos;s own standard, straight after your shift
            </p>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {result.transcript}
          </p>
        </div>

        {/* Shown only when the debrief was not given in English. The rest of
            this product refuses to let a manager act on evidence they cannot
            inspect; the person whose words are being scored gets the same
            right, in their own language, with the terms that were looked up
            named so they can tell us if we read one wrong. */}
        {result.heard && (
          <div className="rounded-2xl border bg-card p-4">
            <div className="flex items-center gap-2">
              <Languages className="size-4 text-primary" />
              <p className="text-sm font-semibold">
                You said it in your own words
              </p>
            </div>
            <p className="mt-2 text-sm italic text-muted-foreground">
              &ldquo;{result.heard.original}&rdquo;
            </p>
            {result.heard.terms.length > 0 && (
              <>
                <p className="mt-3 text-xs font-medium text-muted-foreground">
                  Regional words we looked up
                  {result.heard.country
                    ? `, reading you as ${prettyCountry(result.heard.country)}`
                    : ""}
                </p>
                <ul className="mt-1.5 space-y-1">
                  {result.heard.terms.map((t) => (
                    <li key={t.term} className="text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground">
                        {t.term}
                      </span>{" "}
                      = {t.gloss}
                      {t.ambiguous && (
                        <span className="ml-1 text-[oklch(0.45_0.08_70)]">
                          (means something else elsewhere)
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="mt-3 border-t pt-2 text-xs text-muted-foreground">
              Your manager sees the English above. If we read a word wrong,
              say so, it changes what you get coached on.
            </p>
          </div>
        )}

        <div className="rounded-2xl border border-primary/25 bg-accent/25 p-4">
          <div className="flex items-center gap-2">
            <BookOpen className="size-4 text-primary" />
            <p className="text-xs font-semibold text-primary">
              {result.standard.document} · {result.standard.section_path}
            </p>
          </div>
          <blockquote className="mt-2 border-l-2 border-primary pl-3 text-sm font-medium italic">
            “{result.standard.excerpt}”
          </blockquote>
          <p className="mt-2 text-xs text-muted-foreground">
            Why you&apos;re seeing this: {result.standard.why_shown}
          </p>
        </div>

        {result.generated_scenario_id && (
          <Link
            href={`/staff/practice/${result.generated_scenario_id}`}
            className="group flex items-center gap-3 rounded-2xl border bg-card p-4"
          >
            <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[oklch(0.66_0.055_152)]/15">
              <Sparkles className="size-4 text-[oklch(0.38_0.055_152)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">
                A 3-minute replay was built from what you just said
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Practise it now while it&apos;s fresh, it&apos;s yours, not
                shared.
              </p>
            </div>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
          </Link>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border bg-card p-4">
        <p className="text-sm font-semibold">
          This is just for you and your manager to talk through what actually
          happened.
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          30–90 seconds, in your own words. It never routes to a disciplinary
          path, it&apos;s how you get coaching that&apos;s about your actual
          day.
        </p>
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={submitting || listening || recording}
          placeholder={
            listening
              ? "Listening. Speak your debrief…"
              : "A guest asked for something you weren't sure you could offer, or a moment that still feels off, in your own words…"
          }
          className="mt-3 min-h-28"
        />
        {recording && (
          <p className="mt-3 flex items-center gap-2 text-sm font-medium text-destructive">
            <span className="inline-block size-2 animate-pulse rounded-full bg-destructive" />
            Recording {Math.floor(recorder.seconds / 60)}:
            {String(recorder.seconds % 60).padStart(2, "0")}
            <span className="text-xs font-normal text-muted-foreground">
              tap stop when you&apos;re done
            </span>
          </p>
        )}
        {recorder.state === "denied" && (
          <p className="mt-3 text-xs text-muted-foreground">
            No microphone access, so type it instead, same result.
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {isRealApi() && (
            <Button
              type="button"
              variant={recording ? "destructive" : "default"}
              onClick={() => (recording ? recorder.stop() : void recorder.start())}
              disabled={submitting || listening}
              className="min-w-40 flex-1"
            >
              {recording ? (
                <>
                  <Square className="size-4" />
                  Stop and send
                </>
              ) : (
                <>
                  <Mic className="size-4" />
                  Speak and send
                </>
              )}
            </Button>
          )}
          <Button
            onClick={handleSubmit}
            disabled={submitting || recording}
            variant={isRealApi() ? "outline" : "default"}
            className="min-w-40 flex-1"
          >
            {submitting ? "Checking against your standard…" : "Get instant feedback"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={toggleVoice}
            disabled={submitting}
            aria-label={
              listening ? "Stop dictating" : "Dictate into the box instead"
            }
            aria-pressed={listening}
            title="Dictate into the box, then review before you send"
            className={`shrink-0 rounded-lg ${
              listening
                ? "border-[oklch(0.62_0.09_28)]/50 bg-[oklch(0.7_0.085_28)]/10 text-[oklch(0.44_0.09_28)]"
                : ""
            }`}
          >
            <Captions className={`size-4 ${listening ? "animate-pulse" : ""}`} />
            {listening ? "Stop" : "Dictate"}
          </Button>
        </div>
        {isRealApi() && !recording && !listening && (
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Speak and send writes it up for you. Dictate fills the box so you
            can read it back first.
          </p>
        )}
        {listening && (
          <p
            aria-live="polite"
            className="mt-2 text-center text-xs text-[oklch(0.44_0.09_28)]"
          >
            Listening… your words fill the box. Review, then submit.
          </p>
        )}
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Voice is optional, audio stays on your device and is deleted once
          the transcript is confirmed.
        </p>
      </div>
    </div>
  );
}
