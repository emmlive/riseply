// Thin wrappers over the browser's built-in speech APIs. Everything runs
// on the person's device (no server cost, no audio uploaded), and every
// entry point feature-detects: Firefox has no speech recognition, for
// instance, so callers hide the mic there rather than showing a dead
// button. Server-rendered code must never touch window, hence the guards.

export function dictationSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as any;
  return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function speechSynthesisSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export interface Dictation {
  stop: () => void;
}

// Starts dictation. onText receives the full transcript so far for this
// run (finalized + in-progress), so the caller replaces -- not appends --
// its dictated segment on each call. onEnd fires exactly once.
export function startDictation(
  onText: (text: string) => void,
  onEnd: (error?: string) => void,
): Dictation | null {
  if (!dictationSupported()) return null;
  const w = window as any;
  const Rec = w.SpeechRecognition || w.webkitSpeechRecognition;
  const rec = new Rec();
  rec.lang = navigator.language || "en-US";
  rec.continuous = true;
  rec.interimResults = true;

  let ended = false;
  const finish = (err?: string) => {
    if (ended) return;
    ended = true;
    onEnd(err);
  };

  rec.onresult = (e: any) => {
    let text = "";
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
    onText(text.trim());
  };
  rec.onerror = (e: any) => {
    const code = e?.error as string | undefined;
    if (code === "not-allowed" || code === "service-not-allowed") {
      finish("Microphone access is blocked. Allow it in your browser's site settings to dictate.");
    } else if (code && code !== "no-speech" && code !== "aborted") {
      finish("Dictation stopped unexpectedly — you can type instead.");
    }
  };
  rec.onend = () => finish();

  try {
    rec.start();
  } catch {
    return null;
  }
  return { stop: () => { try { rec.stop(); } catch { /* already stopped */ } } };
}

export function speak(text: string, onEnd?: () => void): void {
  if (!speechSynthesisSupported()) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  synth.speak(u);
}

export function stopSpeaking(): void {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
}
