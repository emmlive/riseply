import { cuesToSpeech } from "@/lib/cues";
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
  let t = cuesToSpeech(text || "");
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

// ---- Voice choice ------------------------------------------------------
// The browser exposes whatever voices the device has installed, so what's on
// offer differs by device (Edge and Chrome on desktop have the most accents).
// The person's pick is remembered on this device.

export interface VoiceInfo {
  uri: string;
  name: string;      // tidied for display
  lang: string;      // e.g. en-GB
  accent: string;    // e.g. British
  natural: boolean;  // a higher-quality "natural"/"neural" voice
  isDefault: boolean;
}

export interface VoicePrefs {
  uri: string;   // "" = device default
  rate: number;  // 0.8 .. 1.3
}

const PREFS_KEY = "cc-voice";
const DEFAULT_PREFS: VoicePrefs = { uri: "", rate: 1 };

export function getVoicePrefs(): VoicePrefs {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(PREFS_KEY) : null;
    if (!raw) return DEFAULT_PREFS;
    const p = JSON.parse(raw);
    const rate = typeof p.rate === "number" ? Math.min(1.5, Math.max(0.6, p.rate)) : 1;
    return { uri: typeof p.uri === "string" ? p.uri : "", rate };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function setVoicePrefs(prefs: VoicePrefs): void {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* private mode: just not remembered */ }
}

const ACCENT_NAMES: Record<string, string> = {
  US: "American", GB: "British", AU: "Australian", IN: "Indian", ZA: "South African", IE: "Irish",
  CA: "Canadian", NZ: "New Zealand", NG: "Nigerian", KE: "Kenyan", GH: "Ghanaian", TZ: "Tanzanian",
  SG: "Singaporean", HK: "Hong Kong", PH: "Filipino", PK: "Pakistani", ZW: "Zimbabwean",
};

export function accentLabel(lang: string): string {
  const region = (lang || "").replace("_", "-").split("-")[1]?.toUpperCase();
  if (!region) return "English";
  if (ACCENT_NAMES[region]) return ACCENT_NAMES[region];
  try {
    const name = new Intl.DisplayNames(["en"], { type: "region" }).of(region);
    if (name) return `${name} English`;
  } catch { /* fall through */ }
  return "English";
}

const NATURAL = /natural|neural|online|premium|enhanced/i;

function tidyName(name: string): string {
  return name
    .replace(/^Microsoft\s+/i, "")
    .replace(/^Google\s+/i, "Google ")
    .replace(/\s+-\s+English.*$/i, "")
    .replace(/\s+Online\s*\(Natural\)/i, " (Natural)")
    .trim();
}

function toInfo(v: SpeechSynthesisVoice): VoiceInfo {
  return {
    uri: v.voiceURI, name: tidyName(v.name), lang: v.lang, accent: accentLabel(v.lang),
    natural: NATURAL.test(v.name), isDefault: v.default,
  };
}

// Voices load asynchronously in most browsers; resolves with the English
// voices (or every voice, if the device has no English one).
export function listVoices(): Promise<VoiceInfo[]> {
  if (!speechSynthesisSupported()) return Promise.resolve([]);
  const synth = window.speechSynthesis;
  const finish = () => {
    const all = synth.getVoices();
    const english = all.filter((v) => /^en([-_]|$)/i.test(v.lang));
    return (english.length ? english : all).map(toInfo);
  };
  return new Promise((resolve) => {
    if (synth.getVoices().length > 0) return resolve(finish());
    let done = false;
    const complete = () => { if (!done) { done = true; synth.removeEventListener?.("voiceschanged", complete); resolve(finish()); } };
    synth.addEventListener?.("voiceschanged", complete);
    setTimeout(complete, 1500);  // some browsers never fire the event
  });
}

// Chrome silently stops long utterances (roughly 15 seconds in) and drops a
// speak() that arrives right after cancel(). So the text is read in
// sentence-sized pieces, queued one after another, and started a beat after
// any cancel. Each call gets a number so a stale piece from an earlier call
// can never end or restart a newer one.
let speakRun = 0;

export function splitForSpeech(text: string, maxLen = 180): string[] {
  const pieces: string[] = [];
  for (const para of (text || "").split(/\n+/)) {
    const sentences = para.match(/[^.!?;:]+[.!?;:]*\s*/g) || [para];
    let buf = "";
    for (const raw of sentences) {
      const sentence = raw.trim();
      if (!sentence) continue;
      if (buf && (buf + " " + sentence).length > maxLen) { pieces.push(buf); buf = ""; }
      if (sentence.length > maxLen) {
        // A very long sentence with no punctuation: cut it at spaces.
        const words = sentence.split(/\s+/);
        let part = "";
        for (const w of words) {
          if (part && (part + " " + w).length > maxLen) { pieces.push(part); part = ""; }
          part = part ? part + " " + w : w;
        }
        buf = part;
      } else {
        buf = buf ? buf + " " + sentence : sentence;
      }
    }
    if (buf) pieces.push(buf);
  }
  return pieces;
}

// The words the voice will say, in order -- what speak() reports positions in.
export function spokenWordList(text: string): string[] {
  return splitForSpeech(cleanForSpeech(text)).join(" ").split(/\s+/).filter(Boolean);
}

// onEnd fires once, when everything has been read or reading stopped.
// onProblem fires if the browser never starts speaking, so the person is
// told instead of left clicking a silent button.
// onWord (optional) is told which word, counted as in spokenWordList(), the
// voice has reached. Browsers that report word boundaries give exact
// positions; for the rest it is estimated from the voice's usual pace.
export function speak(
  text: string, onEnd?: () => void, onProblem?: (message: string) => void, onWord?: (index: number) => void,
): void {
  if (!speechSynthesisSupported()) { onProblem?.("This browser can't read aloud. Try Chrome or Edge."); onEnd?.(); return; }
  const synth = window.speechSynthesis;
  const run = ++speakRun;
  synth.cancel();

  const pieces = splitForSpeech(cleanForSpeech(text));
  if (pieces.length === 0) { onEnd?.(); return; }
  const prefs = getVoicePrefs();
  const counts = pieces.map((p) => p.split(/\s+/).filter(Boolean).length);
  const offsets: number[] = [];
  counts.reduce((sum, c, i) => { offsets[i] = sum; return sum + c; }, 0);
  let finished = false;
  let started = false;
  const done = () => { if (!finished) { finished = true; onEnd?.(); } };

  const speakPiece = (i: number) => {
    if (run !== speakRun) return;               // a newer speak() or a stop took over
    if (i >= pieces.length) { done(); return; }
    const u = new SpeechSynthesisUtterance(pieces[i]);
    u.rate = prefs.rate;
    if (prefs.uri) {
      const voice = synth.getVoices().find((v) => v.voiceURI === prefs.uri);
      if (voice) { u.voice = voice; u.lang = voice.lang; }
    }
    let gotBoundary = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    const stopTimer = () => { if (timer) { clearInterval(timer); timer = null; } };
    u.onstart = () => {
      started = true;
      if (!onWord) return;
      onWord(offsets[i]);
      const t0 = Date.now();
      const estimate = Math.max(600, (pieces[i].length / (15 * prefs.rate)) * 1000);
      timer = setInterval(() => {
        if (run !== speakRun || gotBoundary) { stopTimer(); return; }
        const elapsed = Date.now() - t0;
        if (elapsed < 400) return;   // give real word boundaries a moment to show up
        const frac = Math.min(0.97, elapsed / estimate);
        onWord(offsets[i] + Math.min(counts[i] - 1, Math.floor(frac * counts[i])));
      }, 120);
    };
    u.onboundary = (e: any) => {
      if (!onWord || run !== speakRun) return;
      if (e?.name && e.name !== "word") return;
      gotBoundary = true;
      stopTimer();
      const before = pieces[i].slice(0, e.charIndex || 0).split(/\s+/).filter(Boolean).length;
      onWord(offsets[i] + Math.min(counts[i] - 1, before));
    };
    u.onend = () => { stopTimer(); speakPiece(i + 1); };
    u.onerror = (e: any) => {
      stopTimer();
      if (run !== speakRun) return;
      if (e?.error === "interrupted" || e?.error === "canceled") return;
      if (i === 0 && !started) onProblem?.("Your browser couldn't play the voice. Check the tab isn't muted, or pick a different voice under Voice settings.");
      done();
    };
    synth.speak(u);
  };

  // A beat after cancel(), and resume() in case the engine was left paused.
  setTimeout(() => {
    if (run !== speakRun) return;
    try { synth.resume(); } catch { /* not paused */ }
    speakPiece(0);
    // If nothing has started after a few seconds, say so.
    setTimeout(() => {
      if (run === speakRun && !started && !finished) {
        onProblem?.("Nothing played. Check the tab isn't muted and your sound output is right, then try again.");
        stopSpeaking();
        done();
      }
    }, 4000);
  }, 80);
}

export function stopSpeaking(): void {
  speakRun++;   // makes any queued piece of an earlier speak() do nothing
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
}
