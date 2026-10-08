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

// A speech voice reads every symbol out loud ("asterisk asterisk", "arrow").
// Turn the coach's on-screen text into something that sounds natural.
export function cleanForSpeech(text: string): string {
  let t = text || "";
  t = t.replace(/```[\s\S]*?```/g, " ").replace(/`/g, "");
  t = t.replace(/https?:\/\/\S+/g, "the link");
  t = t.replace(/^[ \t]*(?:-{3,}|\*{3,}|_{3,}|={3,})[ \t]*$/gm, "");          // horizontal rules
  t = t.replace(/^[ \t]{0,3}#{1,6}[ \t]*/gm, "");                              // headings
  t = t.replace(/^[ \t]*(?:[-*\u2022\u25AA\u25CF\u25E6\u2013])[ \t]+/gm, "");  // bullet markers
  t = t.replace(/\*+/g, "");                                                   // bold / italic stars
  t = t.replace(/(^|[\s(])_+|_+(?=[\s).,!?:;]|$)/gm, "$1");                    // emphasis underscores
  t = t.replace(/\s*(?:\u2192|\u21D2|\u279C|\u2794|\u27A1\uFE0F?|->|=>|\u2190|<-)\s*/g, ", ");
  t = t.replace(/\s*\|\s*/g, ", ");
  t = t.replace(/\s*[\u2014\u2013]\s*/g, ", ");
  t = t.replace(/&/g, " and ").replace(/%/g, " percent").replace(/~/g, "");
  t = t.replace(/([A-Za-z0-9])\/(?=[A-Za-z0-9])/g, "$1 ");
  t = t.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}\u{FE0F}\u{200D}\u{2B00}-\u{2BFF}]/gu, "");
  t = t.replace(/[ \t]{2,}/g, " ").replace(/ +([,.;:!?])/g, "$1").replace(/,\s*,/g, ",");
  return t.replace(/\n{3,}/g, "\n\n").trim();
}

export function speak(text: string, onEnd?: () => void): void {
  if (!speechSynthesisSupported()) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(cleanForSpeech(text));
  u.rate = 1;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  synth.speak(u);
}

export function stopSpeaking(): void {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
}
