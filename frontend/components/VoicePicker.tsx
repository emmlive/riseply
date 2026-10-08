"use client";

import { useEffect, useMemo, useState } from "react";
import Fold from "@/components/Fold";
import { getVoicePrefs, listVoices, setVoicePrefs, speak, stopSpeaking, VoiceInfo } from "@/lib/speech";

const SPEEDS = [
  { value: 0.8, label: "Slower" },
  { value: 1, label: "Normal" },
  { value: 1.15, label: "A bit faster" },
  { value: 1.3, label: "Faster" },
];

const SAMPLE = "Hi, I'm your career coach. Let's get you ready for the role you want.";

// Lets the person choose the coach's voice and accent for read-aloud and
// Listen. Choices come from the voices installed on this device.
export default function VoicePicker() {
  const [voices, setVoices] = useState<VoiceInfo[] | null>(null);
  const [uri, setUri] = useState("");
  const [rate, setRate] = useState(1);

  useEffect(() => {
    const prefs = getVoicePrefs();
    setUri(prefs.uri);
    setRate(prefs.rate);
    let cancelled = false;
    listVoices().then((v) => { if (!cancelled) setVoices(v); });
    return () => { cancelled = true; stopSpeaking(); };
  }, []);

  const groups = useMemo(() => {
    const by = new Map<string, VoiceInfo[]>();
    for (const v of voices || []) {
      if (!by.has(v.accent)) by.set(v.accent, []);
      by.get(v.accent)!.push(v);
    }
    const rank = (a: string) => (a === "American" ? 0 : a === "British" ? 1 : 2);
    return [...by.entries()]
      .map(([accent, list]) => [accent, list.sort((a, b) => Number(b.natural) - Number(a.natural) || a.name.localeCompare(b.name))] as const)
      .sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]));
  }, [voices]);

  // A remembered voice that this device no longer has falls back to default.
  const known = uri === "" || (voices || []).some((v) => v.uri === uri);
  const selected = known ? uri : "";

  function choose(nextUri: string, nextRate: number) {
    setUri(nextUri);
    setRate(nextRate);
    setVoicePrefs({ uri: nextUri, rate: nextRate });
  }

  function preview() {
    setVoicePrefs({ uri: selected, rate });
    speak(SAMPLE);
  }

  return (
    <Fold id="voice" title="Coach voice" defaultOpen={false}>
      <div className="cc-voice">
      <p className="hint" style={{ margin: "0 0 10px" }}>
        Pick an accent and speed for read-aloud and the Listen buttons.
      </p>

      {voices === null ? (
        <p className="hint">Loading voices…</p>
      ) : voices.length === 0 ? (
        <p className="hint">This device didn&apos;t offer any voices. Try Chrome or Edge on a computer, or add voices in your device&apos;s speech settings.</p>
      ) : (
        <>
          <label className="cc-label" htmlFor="cc-voice-select">Voice and accent</label>
          <select id="cc-voice-select" className="cc-input" value={selected}
                  onChange={(e) => choose(e.target.value, rate)}>
            <option value="">Device default</option>
            {groups.map(([accent, list]) => (
              <optgroup key={accent} label={`${accent} (${list.length})`}>
                {list.map((v) => (
                  <option key={v.uri} value={v.uri}>{v.name}{v.natural && !/natural/i.test(v.name) ? " (natural)" : ""}</option>
                ))}
              </optgroup>
            ))}
          </select>

          <label className="cc-label" htmlFor="cc-voice-speed" style={{ marginTop: 12 }}>Speed</label>
          <select id="cc-voice-speed" className="cc-input" value={String(rate)}
                  onChange={(e) => choose(selected, Number(e.target.value))}>
            {SPEEDS.map((s) => <option key={s.value} value={String(s.value)}>{s.label}</option>)}
          </select>

          <div className="cc-voice-actions">
            <button className="btn btn-ghost btn-sm" onClick={preview}>▶ Hear a sample</button>
            <button className="btn btn-ghost btn-sm" onClick={stopSpeaking}>■ Stop</button>
          </div>
          <p className="hint" style={{ marginBottom: 0 }}>
            Voices come from your device, so the list differs between computers and phones. Voices marked natural sound the most human.
            Your choice is remembered on this device.
          </p>
        </>
      )}
      </div>
    </Fold>
  );
}
