export class ApiFehler extends Error {
  readonly status: number;
  constructor(meldung: string, status: number) {
    super(meldung);
    this.name = "ApiFehler";
    this.status = status;
  }
}

export interface StartAntwort {
  session_ref: string;
  sdp: string;
  max_dauer_s: number;
}
export interface Kontingent {
  kontingent_knapp: boolean;
  gesperrt: boolean;
}

export interface FrameworkKriterium {
  key: string;
  label: string;
  leitfrage: string;
}
export interface Briefing {
  persona: {
    name: string;
    rolle: string;
    unternehmen: string;
    standorte: string;
    hinweis: string;
  };
  produkt: { name: string; nutzen: string; preis: string };
  ziel: string;
  punkte: string[];
  framework: { id: string; name: string; quelle: string; kriterien: FrameworkKriterium[] };
  max_dauer_s: number;
}

// Schnittstellenentwurf gemäß Plan §10. Bis zum jeweiligen Planschritt ungenutzt;
// Detailformate von Zeit und Punkteposten sind vor der Anbindung abzustimmen.
export type KriteriumStatus = "offen" | "angesprochen";
export interface FrameworkSnapshot {
  revision: number;
  kriterien: Record<string, KriteriumStatus>;
}
export interface AuswertungAnfrage {
  session_ref: string;
  notizen: Record<string, string>;
}
export interface Auswertung {
  kriterien: {
    key: string;
    status: "geklaert" | "teilweise" | "offen";
    wert: string;
    zitat: { text: string; zeit: number } | null;
    tipp: string;
  }[];
  punkte: { posten: { label: string; punkte: number }[]; gesamt: number; max: number };
}

export function sitzungStarten(sdp: string): Promise<StartAntwort> {
  return api<StartAntwort>("/api/session", { sdp }, 25000);
}
export function sitzungBeenden(session_ref: string): Promise<unknown> {
  return api("/api/end", { session_ref });
}

export async function api<T>(pfad: string, daten?: object, zeitlimit = 10000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => {
    ctrl.abort();
  }, zeitlimit);
  try {
    const antwort = await fetch(pfad, {
      method: daten ? "POST" : "GET",
      credentials: "same-origin",
      cache: "no-store",
      signal: ctrl.signal,
      ...(daten
        ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(daten) }
        : {}),
    });
    if (!antwort.ok) {
      let meldung = "Die Anfrage ist fehlgeschlagen. Bitte versuchen Sie es erneut.";
      try {
        const fehler: unknown = await antwort.json();
        if (
          fehler &&
          typeof fehler === "object" &&
          "meldung" in fehler &&
          typeof fehler.meldung === "string"
        ) {
          meldung = fehler.meldung;
        }
      } catch {
        /* Die HTTP-Fehlerbehandlung bleibt auch ohne JSON erhalten. */
      }
      throw new ApiFehler(meldung, antwort.status);
    }
    if (antwort.status === 204) return undefined as T;
    return (await antwort.json()) as T;
  } catch (fehler) {
    if (fehler instanceof ApiFehler) throw fehler;
    throw new ApiFehler(
      ctrl.signal.aborted
        ? "Der Server antwortet nicht rechtzeitig. Bitte versuchen Sie es erneut."
        : "Der Server ist nicht erreichbar. Bitte prüfen Sie Ihre Verbindung und versuchen Sie es erneut.",
      0,
    );
  } finally {
    clearTimeout(timer);
  }
}

export function fehlermeldung(fehler: unknown): string {
  if (fehler instanceof ApiFehler) return fehler.message;
  if (fehler instanceof Error && fehler.name === "NotAllowedError") {
    return "Der Mikrofonzugriff wurde verweigert. Bitte erlauben Sie ihn in den Browser-Einstellungen und starten Sie erneut.";
  }
  if (fehler instanceof Error && fehler.name === "NotFoundError") {
    return "Es wurde kein Mikrofon gefunden. Bitte schließen Sie ein Mikrofon an und starten Sie erneut.";
  }
  return "Die Verbindung konnte nicht aufgebaut werden. Bitte prüfen Sie Mikrofon und Netzwerk und starten Sie erneut.";
}
