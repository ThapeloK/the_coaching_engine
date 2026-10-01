import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Record a spoken note and hand back the audio.
 *
 * Two callers: the staff shift debrief, and the manager's floor observation.
 * Both send the result to our own Whisper endpoint.
 *
 * This is deliberately not the browser's SpeechRecognition API, which
 * use-voice-input.ts uses to help someone type. Two different jobs:
 *
 *  - Dictating into a text box wants live interim results, and losing a word
 *    costs nothing because the person is watching the box.
 *  - A debrief is the record. It has to work on the phone the staff member
 *    actually owns, and SpeechRecognition is Chrome-and-Safari-flavoured,
 *    silently absent on Firefox, and on Chrome it ships the audio to Google
 *    rather than to us. MediaRecorder is everywhere, and the audio goes to our
 *    own Whisper endpoint, which is also the only version of this we can make
 *    a promise about: transcribed, then deleted.
 */

export type RecorderState = "idle" | "recording" | "denied" | "unsupported";

/** Whisper takes both; which one we get depends on the browser. */
function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const type of ["audio/webm", "audio/mp4"]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return undefined;
}

export function extensionFor(mimeType: string): string {
  return mimeType.includes("mp4") ? "m4a" : "webm";
}

export function useRecorder({
  maxSeconds = 120,
  onComplete,
}: {
  maxSeconds?: number;
  onComplete: (blob: Blob, filename: string) => void;
}) {
  const [state, setState] = useState<RecorderState>("idle");
  const [seconds, setSeconds] = useState(0);
  // Loudness, 0 to 1, sampled for the meter. Someone talking into a phone
  // needs to see the thing reacting to their voice, or they stop mid-sentence
  // to check it is on, which is the one thing a twenty second capture cannot
  // afford. Twenty samples a second: smooth to the eye, cheap to render.
  const [level, setLevel] = useState(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const levelTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Read inside the stop handler, which was created before the latest render.
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const cleanup = useCallback(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (levelTimerRef.current) {
      clearInterval(levelTimerRef.current);
      levelTimerRef.current = null;
    }
    void audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    setLevel(0);
    recorderRef.current?.stream.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
  }, []);

  // Releasing the microphone on unmount is not tidiness. A page that navigates
  // away while still holding it leaves the browser's recording indicator lit,
  // which is exactly the kind of thing that makes people stop trusting an app
  // that asks them to talk about their shift.
  useEffect(() => cleanup, [cleanup]);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    const mimeType = pickMimeType();
    if (!mimeType || !navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setState("denied");
      return;
    }

    // Meter the live stream. Wrapped because AudioContext is unavailable or
    // suspended in some embedded webviews, and a missing meter must never stop
    // a recording that is otherwise fine.
    try {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (Ctor) {
        const context = new Ctor();
        audioContextRef.current = context;
        const analyser = context.createAnalyser();
        analyser.fftSize = 256;
        context.createMediaStreamSource(stream).connect(analyser);
        const bins = new Uint8Array(analyser.frequencyBinCount);
        levelTimerRef.current = setInterval(() => {
          analyser.getByteTimeDomainData(bins);
          // Root mean square around the 128 midpoint: a fair measure of how
          // loud it actually is, unlike peak, which pins at 1 on any knock.
          let sum = 0;
          for (let i = 0; i < bins.length; i += 1) {
            const offset = (bins[i] - 128) / 128;
            sum += offset * offset;
          }
          const rms = Math.sqrt(sum / bins.length);
          // Speech sits low in a linear scale; the curve lifts it into the
          // range the eye reads as movement.
          setLevel(Math.min(1, Math.sqrt(rms) * 1.8));
        }, 50);
      }
    } catch {
      // No meter. The recording still works, which is the part that matters.
    }

    chunksRef.current = [];
    const recorder = new MediaRecorder(stream, { mimeType });
    recorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType });
      cleanup();
      setState("idle");
      setSeconds(0);
      if (blob.size > 0) {
        onCompleteRef.current(blob, `debrief.${extensionFor(mimeType)}`);
      }
    };

    recorder.start();
    setState("recording");
    setSeconds(0);
    tickRef.current = setInterval(() => {
      setSeconds((s) => {
        // A hard ceiling, because a phone left in a pocket will happily record
        // the rest of the shift and then fail the upload limit.
        if (s + 1 >= maxSeconds) stop();
        return s + 1;
      });
    }, 1000);
  }, [cleanup, maxSeconds, stop]);

  return { state, seconds, level, start, stop, maxSeconds };
}
