import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult:
    | ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

function getSpeechRecognition(): SpeechRecognitionLike | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

interface UseVoiceInputOptions {
  /** Text appended to the input whenever voice is unavailable or fails hard. */
  demoLine: string;
  /**
   * Called with the full accumulated input — the base text captured when
   * voice started, plus each transcript result — and with demo fills.
   */
  onTranscript: (text: string) => void;
  /**
   * Caller's current input value. Read at the moment the toggle runs, so the
   * hook can capture the base text to append recognition results to.
   */
  getBaseInput: () => string;
  /** When false (e.g. while sending or when turns are exhausted), toggleVoice is a no-op. */
  enabled?: boolean;
  /** Noun in the fallback toasts — "reply" for practice chat, "debrief" for the debrief entry. */
  demoNoun?: string;
}

interface UseVoiceInputReturn {
  listening: boolean;
  toggleVoice: () => void;
  /** Stops an active session without starting one (call before sending). */
  stop: () => void;
}

/**
 * Shared voice-input flow used by the practice chat and the debrief entry.
 *
 * Ask for the mic permission first: starting recognition before the grant
 * fires a spurious "not-allowed" error in Chrome on first use. Recognition
 * is en-US, non-continuous, with interim results; every hard failure path
 * fills the demo line and toasts instead of leaving the user stuck.
 */
export function useVoiceInput({
  demoLine,
  onTranscript,
  getBaseInput,
  enabled = true,
  demoNoun = "reply",
}: UseVoiceInputOptions): UseVoiceInputReturn {
  const [listening, setListening] = useState(false);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  // Base input captured when a session starts; recognition appends to it.
  const baseInputRef = useRef("");
  // Mirrors the input (base + transcript so far) so demo fills land after
  // anything already recognised in the session.
  const currentTextRef = useRef("");
  // Incremented by every stop/invalidation; in-flight starts and recognition
  // callbacks bail when their captured value no longer matches.
  const sessionRef = useRef(0);

  useEffect(() => {
    return () => {
      recRef.current?.abort();
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const stop = () => {
    sessionRef.current += 1;
    const rec = recRef.current;
    recRef.current = null;
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    setListening(false);
    rec?.abort();
  };

  const fillDemo = (message: string) => {
    // Prefer the caller's live value when it diverges from the hook's record
    // (e.g. the user typed mid-session) so a demo fill never wipes edits.
    const live = getBaseInput();
    if (live !== currentTextRef.current) currentTextRef.current = live;
    const next = (currentTextRef.current.trim() ? `${currentTextRef.current.trim()} ` : "") + demoLine;
    currentTextRef.current = next;
    onTranscript(next);
    toast.info(message);
  };

  const toggleVoice = async () => {
    if (listening) {
      stop();
      return;
    }
    if (!enabled) return;
    // Snapshot the caller's input now; it becomes the base for every result
    // in this session, so recognition stays append-only.
    const session = ++sessionRef.current;
    const base = getBaseInput();
    baseInputRef.current = base;
    currentTextRef.current = base;
    const rec = getSpeechRecognition();
    if (!rec) {
      fillDemo(
        `Voice input isn't available in this browser, filled a demo ${demoNoun} instead.`
      );
      return;
    }
    try {
      micStreamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
    } catch {
      if (session !== sessionRef.current) return;
      fillDemo(
        `Microphone access was denied, filled a demo ${demoNoun} instead.`
      );
      return;
    }
    if (session !== sessionRef.current) {
      // stop() ran while the permission prompt was open — release and bail.
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
      return;
    }
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = true;
    rec.onresult = (e) => {
      if (session !== sessionRef.current) return;
      let text = "";
      for (let i = 0; i < e.results.length; i++) {
        const chunk = e.results[i][0]?.transcript ?? "";
        if (chunk) text += (text ? " " : "") + chunk;
      }
      const base = baseInputRef.current.trim();
      const next = (base ? `${base} ` : "") + text.trim();
      currentTextRef.current = next;
      onTranscript(next);
    };
    rec.onend = () => {
      if (session !== sessionRef.current) return;
      recRef.current = null;
      setListening(false);
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    };
    rec.onerror = (e) => {
      if (session !== sessionRef.current) return;
      if (recRef.current !== rec) return;
      recRef.current = null;
      setListening(false);
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
      if (e.error === "network" || e.error === "service-not-allowed") {
        fillDemo(
          `Voice recognition failed (${e.error}), filled a demo ${demoNoun} instead.`
        );
      } else {
        toast.error("Didn't catch that, please try again or type.");
      }
    };
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  return { listening, toggleVoice, stop };
}
