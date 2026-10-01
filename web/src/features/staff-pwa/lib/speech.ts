"use client";

/**
 * Speaking a guest line when there is no synthesised audio for it.
 *
 * The chat already offers "hear it" whenever the backend returned an
 * ElevenLabs clip, and that is the better voice, so it stays first. But the
 * voice budget holds back a reserve and stops synthesising long before the
 * account is empty, which is the normal state of this product on a free tier:
 * audio_id comes back null, GuestAudio rendered nothing, and the feature
 * silently did not exist. A guest who is only annoyed in writing is exactly
 * the thing this practice is meant to train against.
 *
 * So this is the fallback: the browser's own speech synthesis. It costs
 * nothing, needs no network, and every modern browser has it. It is worse than
 * ElevenLabs and it is much better than silence.
 */

export type SpeechSupport = "ready" | "unsupported";

export function speechSupport(): SpeechSupport {
  if (typeof window === "undefined") return "unsupported";
  return "speechSynthesis" in window ? "ready" : "unsupported";
}

/**
 * Pick a voice once, and prefer one that sounds like a hotel guest in Ireland
 * or the UK rather than whatever the OS happens to list first, which on
 * Windows is often a US voice and on Android is frequently robotic.
 *
 * getVoices() is empty on first call in Chrome until the voiceschanged event
 * fires, so this is called lazily at speak time rather than cached at module
 * load.
 */
function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const byPreference = [
    (v: SpeechSynthesisVoice) => v.lang === "en-IE",
    (v: SpeechSynthesisVoice) => v.lang === "en-GB",
    (v: SpeechSynthesisVoice) => v.lang.startsWith("en"),
  ];
  for (const test of byPreference) {
    const found = voices.find(test);
    if (found) return found;
  }
  return voices[0] ?? null;
}

interface SpeakOptions {
  onStart?: () => void;
  onEnd?: () => void;
}

/**
 * Speak one line, cancelling anything already speaking.
 *
 * Cancelling first matters: queued utterances are the default behaviour, so
 * tapping three bubbles in a row would otherwise read all three, one after the
 * other, with no way to stop except waiting.
 */
export function speak(text: string, options: SpeakOptions = {}): void {
  if (speechSupport() !== "ready" || !text.trim()) return;
  const synth = window.speechSynthesis;
  synth.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickVoice();
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang;
  }
  // Slightly under the default. A complaint delivered at newsreader speed
  // sounds like a recording; this sounds like somebody talking to you.
  utterance.rate = 0.95;
  utterance.pitch = 1;

  utterance.onstart = () => options.onStart?.();
  utterance.onend = () => options.onEnd?.();
  utterance.onerror = () => options.onEnd?.();

  synth.speak(utterance);
}

export function stopSpeaking(): void {
  if (speechSupport() !== "ready") return;
  window.speechSynthesis.cancel();
}
