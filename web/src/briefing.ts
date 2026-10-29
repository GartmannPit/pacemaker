import type { Briefing, FrameworkKriterium } from "./api.ts";

export interface BriefingModell {
  titel: string;
  ziel: string;
  name: string;
  beschreibung: string;
  produkt: string;
  fakten: { label: string; wert: string }[];
  dauer: string;
  hinweis: string;
  framework: string;
  quelle: string;
  kriterien: (FrameworkKriterium & { status: "offen"; gespraechStatus: "folgt" })[];
  punkte: string[];
}

// Ausschließlich öffentliche Serverangaben; keine Werte oder Treffer ergänzen.
export function briefingModell(briefing: Briefing): BriefingModell {
  const { persona, produkt, framework } = briefing;
  const verkauf = `${produkt.name} – ${produkt.nutzen}`;
  return {
    titel: `Rufen Sie ${persona.name} an.`,
    ziel: briefing.ziel,
    name: persona.name,
    beschreibung: `${persona.rolle} · ${persona.unternehmen} · ${persona.standorte}`,
    produkt: verkauf,
    fakten: [
      { label: "Gesprächspartner", wert: `${persona.name}, ${persona.rolle}` },
      { label: "Unternehmen", wert: persona.unternehmen },
      { label: "Standorte", wert: persona.standorte },
      { label: "Ihr Produkt", wert: verkauf },
      { label: "Preis", wert: produkt.preis },
    ],
    dauer: `${new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 }).format(briefing.max_dauer_s / 60)} Minuten`,
    hinweis: persona.hinweis,
    framework: framework.name,
    quelle: framework.quelle,
    kriterien: framework.kriterien.map((kriterium) => ({
      ...kriterium,
      status: "offen",
      gespraechStatus: "folgt",
    })),
    punkte: [...briefing.punkte],
  };
}

// Kein Request- oder Persistenzzugriff. Der gemeinsame Löschpfad des Gesprächs
// verwirft diese Notizen bei Neustart, Abmelden, 401 und Verlassen der Seite.
export class Notizen {
  private werte = new Map<string, string>();

  setzen(key: string, text: string): void {
    this.werte.set(key, text);
  }
  lesen(key: string): string {
    return this.werte.get(key) ?? "";
  }
  ausgefuellt(keys: readonly string[]): number {
    return keys.filter((key) => this.lesen(key).trim().length > 0).length;
  }
  leeren(): void {
    this.werte.clear();
  }
}
