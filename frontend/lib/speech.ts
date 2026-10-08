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

export function speak(text: string, onEnd?: () => void): void {
  if (!speechSynthesisSupported()) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(cleanForSpeech(text));
  const prefs = getVoicePrefs();
  u.rate = prefs.rate;
  if (prefs.uri) {
    const voice = synth.getVoices().find((v) => v.voiceURI === prefs.uri);
    if (voice) { u.voice = voice; u.lang = voice.lang; }
  }
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  synth.speak(u);
}

export function stopSpeaking(): void {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
}
