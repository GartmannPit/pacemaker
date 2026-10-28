export interface Uhr {
  jetzt(): number;
  setzen(aufgabe: () => void, ms: number): () => void;
}

export const systemUhr: Uhr = {
  jetzt: () => Date.now(),
  setzen(aufgabe, ms) {
    const timer = setTimeout(aufgabe, ms);
    return () => {
      clearTimeout(timer);
    };
  },
};

export type EndeGrund =
  | "nutzer"
  | "auflegen"
  | "zeitlimit"
  | "inaktiv"
  | "tab_geschlossen"
  | "verbindung_verloren"
  | "herzschlag_fehlt"
  | "sideband_abbruch"
  | "attach_fehler"
  | "server_ende"
  | "wiederanlauf";

export interface HerzAntwort {
  zustand: "laufend" | "endend" | "beendet";
  grund: EndeGrund | null;
}

export type HerzEnde =
  { art: "ende"; grund: EndeGrund | null } | { art: "anmeldung" } | { art: "frist" };

export function istHerzAntwort(wert: unknown): wert is HerzAntwort {
  if (!wert || typeof wert !== "object") return false;
  if (!("zustand" in wert) || !("grund" in wert)) return false;
  return (
    ["laufend", "endend", "beendet"].includes(String(wert.zustand)) &&
    (wert.grund === null ||
      (typeof wert.grund === "string" &&
        [
          "nutzer",
          "auflegen",
          "zeitlimit",
          "inaktiv",
          "tab_geschlossen",
          "verbindung_verloren",
          "herzschlag_fehlt",
          "sideband_abbruch",
          "attach_fehler",
          "server_ende",
          "wiederanlauf",
        ].includes(wert.grund)))
  );
}

// Jeder Aufruf besitzt eigene Timer und einen eigenen Anfragekontext. Ein Stop macht
// auch Antworten unwirksam, deren fetch-Implementierung das Abbruchsignal ignoriert.
export function herzschlagStarten(
  sessionRef: string,
  ende: (ereignis: HerzEnde) => void,
  optionen: { uhr?: Uhr; fetch?: typeof fetch } = {},
): () => void {
  const uhr = optionen.uhr ?? systemUhr;
  const anfragen = optionen.fetch ?? fetch;
  let aktiv = true;
  let bestaetigt = uhr.jetzt();
  let letzterVersuch = uhr.jetzt();
  let offen: AbortController | null = null;
  let taktStop = () => {};
  let fristStop = () => {};
  let anfrageStop = () => {};

  function ungueltig(ctrl: AbortController): boolean {
    return !aktiv || ctrl.signal.aborted;
  }
  function stoppen() {
    aktiv = false;
    taktStop();
    fristStop();
    anfrageStop();
    offen?.abort();
  }
  function abschliessen(ereignis: HerzEnde) {
    if (!aktiv) return;
    stoppen();
    ende(ereignis);
  }
  function fristPlanen() {
    fristStop();
    fristStop = uhr.setzen(() => {
      abschliessen({ art: "frist" });
    }, 15000);
  }
  async function senden() {
    const ctrl = new AbortController();
    offen = ctrl;
    letzterVersuch = uhr.jetzt();
    // Die offene Anfrage bleibt bis zur tatsächlichen Erledigung gesperrt, auch
    // wenn ein Transport Abort ignoriert. Die lokale Frist läuft unabhängig weiter.
    anfrageStop = uhr.setzen(() => {
      ctrl.abort();
    }, 4000);
    try {
      const antwort = await anfragen("/api/herzschlag", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ref: sessionRef }),
        signal: ctrl.signal,
      });
      if (ungueltig(ctrl)) return;
      if (uhr.jetzt() - bestaetigt >= 15000) {
        abschliessen({ art: "frist" });
        return;
      }
      if (antwort.status === 401) abschliessen({ art: "anmeldung" });
      else if (antwort.status === 404) abschliessen({ art: "ende", grund: null });
      else if (antwort.ok) {
        const daten: unknown = await antwort.json();
        if (ungueltig(ctrl)) return;
        if (uhr.jetzt() - bestaetigt >= 15000) {
          abschliessen({ art: "frist" });
        } else if (istHerzAntwort(daten)) {
          if (daten.zustand !== "laufend") abschliessen({ art: "ende", grund: daten.grund });
          else {
            bestaetigt = uhr.jetzt();
            fristPlanen();
          }
        }
      }
    } catch {
      // Netzfehler, ungültiges JSON und 5xx werden bis zur lokalen Frist toleriert.
    } finally {
      if (offen === ctrl) {
        anfrageStop();
        offen = null;
      }
    }
  }
  function takt() {
    if (!aktiv) return;
    if (uhr.jetzt() - bestaetigt >= 15000) {
      abschliessen({ art: "frist" });
      return;
    }
    if (!offen && uhr.jetzt() - letzterVersuch >= 5000) void senden();
    taktStop = uhr.setzen(takt, 1000);
  }
  fristPlanen();
  taktStop = uhr.setzen(takt, 1000);
  return stoppen;
}
