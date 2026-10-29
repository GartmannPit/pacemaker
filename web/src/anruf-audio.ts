import type { Analyse, AnrufAudio } from "./gespraech.ts";
import { AudioDetektor } from "./detektor.ts";

// Ausgabe: ausschließlich der Wählton an destination. Analyse: ausschließlich
// MediaStreamSource → Analyser, ohne destination. Persona-Wiedergabe bleibt <audio>.
export function anrufAudioStarten(
  erkannt: () => void,
  aenderung: () => void,
  visualisieren: (context: AudioContext) => Analyse,
): AnrufAudio {
  const context = new AudioContext();
  let aktiv = true;
  let visual: Analyse;
  try {
    visual = visualisieren(context);
  } catch {
    visual = { mikrofon() {}, remote() {}, stop() {} };
  }
  const detektor = new AudioDetektor();
  let quelle: MediaStreamAudioSourceNode | null = null;
  let analyser: AnalyserNode | null = null;
  let daten: Float32Array<ArrayBuffer> | null = null;
  let analyseTimer: ReturnType<typeof setTimeout> | null = null;
  let detektorAktiv = false;
  let waehlt = false;
  let tonTimer: ReturnType<typeof setTimeout> | null = null;
  const toene = new Set<OscillatorNode>();
  const verstaerker = new Set<GainNode>();
  context.onstatechange = () => {
    if (aktiv) aenderung();
  };
  // Aufruf synchron aus der Startgeste. Eine Ablehnung ist kein unhandled rejection.
  void context.resume().then(
    () => {
      if (aktiv) aenderung();
    },
    () => {
      if (aktiv) aenderung();
    },
  );

  function ruhe() {
    waehlt = false;
    if (tonTimer !== null) clearTimeout(tonTimer);
    tonTimer = null;
    for (const ton of toene) {
      try {
        ton.stop();
      } catch {
        /* Bereits beendet. */
      }
      ton.disconnect();
    }
    toene.clear();
    for (const gain of verstaerker) gain.disconnect();
    verstaerker.clear();
  }
  function ton(frequenzen: number[], start: number, dauer: number) {
    if (!aktiv || !waehlt) return;
    const gain = context.createGain();
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(0.055, start + 0.008);
    gain.gain.setValueAtTime(0.055, start + dauer - 0.008);
    gain.gain.linearRampToValueAtTime(0, start + dauer);
    gain.connect(context.destination);
    verstaerker.add(gain);
    let rest = frequenzen.length;
    for (const hz of frequenzen) {
      const oszillator = context.createOscillator();
      oszillator.frequency.value = hz;
      oszillator.connect(gain);
      toene.add(oszillator);
      oszillator.onended = () => {
        toene.delete(oszillator);
        oszillator.disconnect();
        if (--rest === 0) {
          gain.disconnect();
          verstaerker.delete(gain);
        }
      };
      oszillator.start(start);
      oszillator.stop(start + dauer);
    }
  }
  function freizeichen() {
    if (!aktiv || !waehlt) return;
    ton([425], context.currentTime, 1);
    tonTimer = setTimeout(freizeichen, 5000);
  }
  function messen() {
    if (!aktiv || !analyser || !daten) return;
    try {
      if (context.state === "running") {
        analyser.getFloatTimeDomainData(daten);
        let summe = 0;
        for (const wert of daten) summe += wert * wert;
        if (detektor.pruefen(Math.sqrt(summe / daten.length), performance.now())) {
          erkannt();
          return;
        }
      } else detektor.pruefen(0, performance.now());
    } catch {
      detektorAktiv = false;
      aenderung();
      return;
    }
    analyseTimer = setTimeout(messen, 20);
  }
  return {
    laeuft: () => aktiv && context.state === "running",
    detektor: () => detektorAktiv && context.state === "running",
    async freigeben() {
      try {
        await context.resume();
        return aktiv && context.state === "running";
      } catch {
        return false;
      }
    },
    mikrofon(stream) {
      visual.mikrofon(stream);
    },
    remote(stream) {
      visual.remote(stream);
      if (!aktiv) return;
      if (analyseTimer !== null) clearTimeout(analyseTimer);
      quelle?.disconnect();
      analyser?.disconnect();
      try {
        quelle = context.createMediaStreamSource(stream);
        analyser = context.createAnalyser();
        analyser.fftSize = 1024;
        daten = new Float32Array(analyser.fftSize);
        quelle.connect(analyser);
        detektorAktiv = true;
        messen();
      } catch {
        detektorAktiv = false;
      }
    },
    waehlen() {
      ruhe();
      waehlt = true;
      const start = context.currentTime;
      [
        [697, 1209],
        [770, 1336],
        [852, 1477],
      ].forEach((hz, index) => {
        ton(hz, start + index * 0.19, 0.12);
      });
      tonTimer = setTimeout(freizeichen, 650);
    },
    ruhe,
    stop() {
      aktiv = false;
      ruhe();
      try {
        visual.stop();
      } catch {
        /* Der optionale Pegelzweig verhindert kein Aufräumen. */
      }
      if (analyseTimer !== null) clearTimeout(analyseTimer);
      quelle?.disconnect();
      analyser?.disconnect();
      quelle = null;
      analyser = null;
      daten = null;
      detektorAktiv = false;
      context.onstatechange = null;
      void context.close().catch(() => {});
    },
  };
}
