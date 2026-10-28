import type { Analyse } from "./gespraech.ts";

export const PEGEL_AKTIV: boolean = true;

export interface Pegel extends Analyse {
  aktivieren(aktiv: boolean): boolean;
}

// Analysezweige enden im AnalyserNode. Die Audioausgabe läuft ausschließlich
// über das Audioelement; weder destination noch createMediaElementSource verwenden.
export function pegelStarten(
  canvas: HTMLCanvasElement,
  werte: (eigen: number, brandt: number) => void,
  verfuegbar: (aktiv: boolean) => void,
): Pegel {
  let aktiv = true;
  let anzeigen = PEGEL_AKTIV && new URLSearchParams(location.search).get("pegel") !== "0";
  let context: AudioContext | null = null;
  const nodes: AudioNode[] = [];
  let eigen: AnalyserNode | null = null;
  let remote: AnalyserNode | null = null;
  let eigenDaten: Uint8Array<ArrayBuffer> | null = null;
  let remoteDaten: Uint8Array<ArrayBuffer> | null = null;
  let frame = 0;
  let niveau = 0;
  let breite = 0;
  let hoehe = 0;
  let meldung = false;
  let letzterWert = 0;
  const reduziert = matchMedia("(prefers-reduced-motion: reduce)");
  const cx = canvas.getContext("2d");

  function zeichnen(zeit = 0) {
    if (!cx) return;
    cx.clearRect(0, 0, breite, hoehe);
    const x = breite / 2,
      y = hoehe * 0.39,
      radius = Math.min(breite, hoehe) * 0.2;
    if (radius <= 0) return;
    const bewegung = reduziert.matches || !anzeigen ? 0 : niveau;
    const licht = cx.createRadialGradient(x, y, radius * 0.2, x, y, radius * 2.6);
    licht.addColorStop(0, "#2433d62b");
    licht.addColorStop(1, "#2433d600");
    cx.fillStyle = licht;
    cx.fillRect(0, 0, breite, hoehe);
    for (let ring = 0; ring < 3; ring++) {
      cx.beginPath();
      for (let i = 0; i <= 160; i++) {
        const winkel = (i / 160) * Math.PI * 2;
        const wellen =
          Math.sin(winkel * 3 + zeit * 0.002 + ring) * 0.5 +
          Math.sin(winkel * 7 - zeit * 0.001) * 0.25;
        const r =
          radius * (1 + ring * 0.16) + bewegung * radius * (0.18 - ring * 0.045) * (1 + wellen);
        const px = x + Math.cos(winkel) * r,
          py = y + Math.sin(winkel) * r;
        if (i === 0) cx.moveTo(px, py);
        else cx.lineTo(px, py);
      }
      cx.strokeStyle = ring === 0 ? "#2433d6" : "#6b78f0";
      cx.globalAlpha = ring === 0 ? 0.95 : 0.4 - ring * 0.08;
      cx.lineWidth = ring === 0 ? 3 : 1.5;
      cx.stroke();
    }
    cx.globalAlpha = 1;
    cx.beginPath();
    cx.arc(x, y, radius * 0.82, 0, Math.PI * 2);
    cx.fillStyle = "#2433d61c";
    cx.fill();
    cx.fillStyle = "#2433d6";
    cx.font = `700 ${String(Math.round(radius * 0.5))}px Bricolage, sans-serif`;
    cx.textAlign = "center";
    cx.textBaseline = "middle";
    cx.fillText("MB", x, y);
  }
  const beobachter = new ResizeObserver(([eintrag]) => {
    if (!aktiv || !eintrag) return;
    breite = eintrag.contentRect.width;
    hoehe = eintrag.contentRect.height;
    const dichte = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(breite * dichte);
    canvas.height = Math.round(hoehe * dichte);
    cx?.setTransform(dichte, 0, 0, dichte, 0, 0);
    zeichnen();
  });
  beobachter.observe(canvas);
  function zustand() {
    const bereit = anzeigen && context?.state === "running";
    if (bereit !== meldung) {
      meldung = bereit;
      verfuegbar(bereit);
    }
  }
  function ausfall() {
    eigen = null;
    remote = null;
    eigenDaten = null;
    remoteDaten = null;
    verfuegbar(false);
  }
  // Synchron im Start-Klick, vor der ersten Mikrofon-Promise.
  if (anzeigen) {
    try {
      context = new AudioContext();
      context.onstatechange = zustand;
      void context.resume().then(
        () => {
          if (aktiv) zustand();
        },
        () => {
          if (aktiv) ausfall();
        },
      );
    } catch {
      context = null;
      verfuegbar(false);
    }
  } else verfuegbar(false);

  function quelle(stream: MediaStream, istEigen: boolean) {
    if (!aktiv || !context) return;
    try {
      const source = context.createMediaStreamSource(stream);
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      nodes.push(source, analyser);
      if (istEigen) {
        eigen = analyser;
        eigenDaten = new Uint8Array(analyser.fftSize);
      } else {
        remote = analyser;
        remoteDaten = new Uint8Array(analyser.fftSize);
      }
    } catch {
      ausfall();
    }
  }
  function lautstaerke(analyser: AnalyserNode | null, daten: Uint8Array<ArrayBuffer> | null) {
    if (!analyser || !daten || context?.state !== "running") return 0;
    analyser.getByteTimeDomainData(daten);
    let summe = 0;
    for (const wert of daten) summe += ((wert - 128) / 128) ** 2;
    return Math.min(1, Math.sqrt(summe / daten.length) * 6);
  }
  function messen(zeit: number) {
    if (!aktiv) return;
    try {
      const e = anzeigen ? lautstaerke(eigen, eigenDaten) : 0;
      const r = anzeigen ? lautstaerke(remote, remoteDaten) : 0;
      niveau += (r - niveau) * 0.18;
      if (zeit - letzterWert >= 100) {
        letzterWert = zeit;
        werte(e, r);
      }
      zeichnen(zeit);
    } catch {
      ausfall();
    }
    if (anzeigen && context) frame = requestAnimationFrame(messen);
  }
  if (anzeigen && context) frame = requestAnimationFrame(messen);
  return {
    mikrofon: (stream) => {
      quelle(stream, true);
    },
    remote: (stream) => {
      quelle(stream, false);
    },
    aktivieren(wert) {
      anzeigen = wert && context !== null;
      cancelAnimationFrame(frame);
      niveau = 0;
      zustand();
      werte(0, 0);
      if (anzeigen) frame = requestAnimationFrame(messen);
      else zeichnen();
      return anzeigen;
    },
    stop() {
      aktiv = false;
      cancelAnimationFrame(frame);
      beobachter.disconnect();
      for (const node of nodes) {
        try {
          node.disconnect();
        } catch {
          /* Bereits getrennt. */
        }
      }
      nodes.length = 0;
      eigen = null;
      remote = null;
      eigenDaten = null;
      remoteDaten = null;
      if (context) {
        context.onstatechange = null;
        void context.close().catch(() => {});
        context = null;
      }
      cx?.clearRect(0, 0, breite, hoehe);
    },
  };
}
