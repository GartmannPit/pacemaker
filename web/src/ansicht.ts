import { abschlussText } from "./gespraech.ts";
import type { Phase, Rolle, Zustand } from "./gespraech.ts";
import { briefingModell, Notizen } from "./briefing.ts";
import type { Briefing } from "./api.ts";

function textElement(tag: string, text: string, klasse = ""): HTMLElement {
  const el = document.createElement(tag);
  el.textContent = text;
  el.className = klasse;
  return el;
}

// Der Aufrufer kennt den konkreten Typ des statisch angelegten Elements.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
export function element<T extends HTMLElement = HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Element fehlt: ${id}`);
  return el as T;
}
export function zeit(ms: number): string {
  const sekunden = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(sekunden / 60)).padStart(2, "0")}:${String(sekunden % 60).padStart(2, "0")}`;
}

export class Ansicht {
  private notizen = new Notizen();
  private personaName = "Ihr Gegenüber";
  private phase: Phase | null = null;
  private zeile: { rolle: Rolle; text: HTMLParagraphElement } | null = null;
  private sprecher: Rolle | null = null;
  private deltaSprecher: Rolle | null = null;
  private deltaZeit = -Infinity;
  private pegelZeit = -Infinity;
  private kriterien: string[] = [];

  status(meldung: string) {
    const status = element("status");
    if (status.textContent !== meldung) status.textContent = meldung;
  }
  ansage(text: string) {
    element("timer-ansage").textContent = text;
  }
  private ansicht(id: string) {
    for (const name of [
      "anmeldung",
      "bereit",
      "mikrofon_anfrage",
      "briefing",
      "anwaehlen",
      "sitzung",
      "ausfuellen",
      "scoreboard",
    ]) {
      element(name).hidden = name !== id;
      element(name).inert = name !== id;
    }
  }
  anmeldung(meldung: string) {
    this.phase = null;
    this.leeren();
    this.personaName = "Ihr Gegenüber";
    this.kriterien = [];
    for (const id of [
      "frameworks",
      "briefing-ziel",
      "briefing-fakten",
      "briefing-hinweis",
      "briefing-dauer",
      "briefing-aufgaben",
      "briefing-kriterien",
      "gespraech-aufgaben",
      "gespraech-kriterien",
      "persona-name",
      "auswertung-notizen",
      "framework-name",
      "framework-quelle",
      "kriterien-titel",
    ])
      element(id).replaceChildren();
    this.ansicht("anmeldung");
    element("ton-hilfe").hidden = true;
    element("abmelden").hidden = true;
    element("transkript-knopf").hidden = true;
    element("nutzer").textContent = "";
    this.status(meldung);
    element("anmeldung-titel").focus();
  }
  bereit(name: string) {
    this.phase = "bereit";
    this.leeren();
    this.ansicht("bereit");
    element("nutzer").textContent = name;
    element("abmelden").hidden = false;
    element("transkript-knopf").hidden = true;
    this.status("Ihr Briefing wird geladen …");
    element("start").focus();
  }
  briefing(daten: Briefing) {
    const modell = briefingModell(daten);
    this.personaName = modell.name;
    this.kriterien = modell.kriterien.map((k) => k.key);
    element("frameworks").replaceChildren(
      textElement("legend", "Framework"),
      ...daten.frameworks.map((f) => {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "framework";
        input.value = f.id;
        input.disabled = !f.verfuegbar;
        input.checked = f.id === daten.framework.id && f.verfuegbar;
        label.className = f.verfuegbar ? "framework-wahl" : "framework-wahl nicht-verfuegbar";
        label.append(input, textElement("strong", f.name));
        if (!f.verfuegbar) label.append(textElement("span", "In Vorbereitung", "klein"));
        return label;
      }),
    );
    element("briefing-titel").textContent = modell.titel;
    element("briefing-ziel").textContent = `Ihr Ziel: ${modell.ziel}`;
    element("persona-name").textContent = modell.name;
    element("briefing-fakten").replaceChildren(
      ...modell.fakten.flatMap(({ label, wert }) => [
        textElement("dt", label),
        textElement("dd", wert),
      ]),
    );
    element("briefing-dauer").textContent = modell.dauer;
    element("briefing-hinweis").textContent = modell.hinweis;
    element("framework-name").textContent = modell.framework;
    element("framework-quelle").textContent = modell.quelle;
    element("kriterien-titel").textContent = modell.framework;
    for (const id of ["briefing-aufgaben", "gespraech-aufgaben"])
      element(id).replaceChildren(...daten.aufgaben.map((a) => textElement("li", a)));
    for (const id of ["briefing-kriterien", "gespraech-kriterien"])
      element(id).replaceChildren(
        ...modell.kriterien.map((k) => {
          const zeile = textElement("li", "", "kriterium");
          const inhalt = textElement("div", "");
          inhalt.append(textElement("strong", k.label), textElement("p", k.leitfrage, "klein"));
          zeile.append(textElement("span", k.key, "kriterium-key"), inhalt);
          return zeile;
        }),
      );
    element("auswertung-notizen").replaceChildren(
      ...modell.kriterien.map((k, index) => {
        const zeile = textElement("div", "", "notiz");
        const inhalt = textElement("div", "");
        const label = document.createElement("label");
        label.htmlFor = `notiz-${String(index)}`;
        label.textContent = `${k.label} – Was haben Sie erfahren?`;
        const feld = document.createElement("textarea");
        feld.id = label.htmlFor;
        feld.name = label.htmlFor;
        feld.autocomplete = "off";
        feld.rows = 3;
        feld.setAttribute("aria-describedby", "notizen-hinweis");
        feld.addEventListener("input", () => {
          this.notizen.setzen(k.key, feld.value);
        });
        inhalt.append(label, feld);
        zeile.append(textElement("span", k.key, "kriterium-key"), inhalt);
        return zeile;
      }),
    );
  }
  framework(): string | null {
    return (
      element("frameworks").querySelector<HTMLInputElement>("input:checked:not(:disabled)")
        ?.value ?? null
    );
  }
  gegenueber(): string {
    return this.personaName;
  }
  schublade(offen: boolean) {
    const knopf = element("transkript-knopf");
    const drawer = element("transkript");
    const fokusImDrawer = drawer.contains(document.activeElement);
    drawer.hidden = !offen;
    drawer.inert = !offen;
    knopf.setAttribute("aria-expanded", String(offen));
    knopf.textContent = offen ? "Transkript ausblenden" : "Transkript einblenden";
    element("gespraech-layout").classList.toggle("offen", offen);
    if (offen) element("transkript-titel").focus();
    else if (fokusImDrawer) knopf.focus();
  }
  leeren() {
    this.notizen.leeren();
    for (const feld of element("auswertung-notizen").querySelectorAll("textarea")) feld.value = "";
    for (const id of [
      "abschluss-text",
      "ergebnis-dauer",
      "ergebnis-grund",
      "ergebnis-felder",
      "timer-ansage",
    ])
      element(id).textContent = "";
    this.zeile = null;
    this.deltaSprecher = null;
    this.sprecher = null;
    this.deltaZeit = -Infinity;
    this.pegelZeit = -Infinity;
    element("transkript-inhalt").replaceChildren(
      textElement(
        "p",
        "Sobald Sie oder Ihr Gegenüber sprechen, erscheint hier das Transkript.",
        "klein",
      ),
    );
    element("transkript-inhalt").firstElementChild?.setAttribute("id", "transkript-leer");
    this.schublade(false);
  }
  transkript(rolle: Rolle, delta: string) {
    if (!delta) return;
    const inhalt = element("transkript-inhalt");
    const unten = inhalt.scrollHeight - inhalt.scrollTop - inhalt.clientHeight < 60;
    document.getElementById("transkript-leer")?.remove();
    if (this.zeile?.rolle !== rolle) {
      const zeile = document.createElement("div");
      zeile.className = `transkript-zeile ${rolle}`;
      const name = document.createElement("strong");
      name.textContent = rolle === "sie" ? "Sie" : this.personaName;
      const text = document.createElement("p");
      zeile.append(name, text);
      inhalt.append(zeile);
      this.zeile = { rolle, text };
    }
    this.zeile.text.textContent += delta;
    if (unten) inhalt.scrollTop = inhalt.scrollHeight;
    this.deltaSprecher = rolle;
    this.deltaZeit = performance.now();
    this.sprecherPruefen();
  }
  pegel(eigen: number, brandt: number) {
    if (eigen > 0.08 || brandt > 0.08) {
      this.pegelZeit = performance.now();
      this.sprecherSetzen(brandt >= eigen ? "brandt" : "sie");
    } else this.sprecherPruefen();
  }
  private sprecherPruefen() {
    if (performance.now() - this.pegelZeit < 500) return;
    this.sprecherSetzen(performance.now() - this.deltaZeit < 1400 ? this.deltaSprecher : null);
  }
  private sprecherSetzen(rolle: Rolle | null) {
    if (this.phase !== "gespraech" || this.sprecher === rolle) return;
    this.sprecher = rolle;
    element("sprecher").textContent =
      rolle === "brandt"
        ? `${this.personaName} spricht`
        : rolle === "sie"
          ? "Sie sprechen"
          : "Verbunden · Gesprächspause";
  }
  aktualisieren(wert: Zustand) {
    const wechsel = wert.phase !== this.phase;
    this.phase = wert.phase;
    this.ansicht(wert.phase === "gespraech" ? "sitzung" : wert.phase);
    if (wechsel) this.schublade(false);
    this.status(wert.meldung);
    element("transkript-knopf").hidden = wert.phase !== "gespraech";
    if (["anwaehlen", "gespraech"].includes(wert.phase)) {
      const ziel = element(wert.phase === "anwaehlen" ? "anwaehlen" : "anruf-ton");
      if (element("ton-hilfe").parentElement !== ziel) ziel.append(element("ton-hilfe"));
    }
    element("ton-hilfe").hidden =
      !wert.tonBlockiert || !["anwaehlen", "gespraech"].includes(wert.phase);
    if (wert.phase === "briefing" || wert.phase === "scoreboard") {
      const prefix = wert.phase === "briefing" ? "briefing" : "ergebnis";
      element(`${prefix}-countdown`).textContent = String(wert.countdown ?? "");
      element(`${prefix}-pause`).textContent = wert.pausiert ? "Fortsetzen" : "Anhalten";
      element(`${prefix}-pause`).setAttribute("aria-pressed", String(wert.pausiert));
      element(`${prefix}-timer-text`).textContent = wert.pausiert
        ? "Angehalten"
        : wert.phase === "briefing"
          ? "Sekunden bis zum Anruf"
          : "Sekunden bis zum Start";
    }
    if (wert.phase === "gespraech") {
      element("restzeit").textContent = zeit(wert.restzeit ?? 0);
      this.sprecherPruefen();
    }
    if (wert.phase === "ausfuellen") element("abschluss-text").textContent = wert.meldung;
    if (wert.phase === "scoreboard" && wert.abschluss) {
      element("ergebnis-dauer").textContent = zeit(wert.abschluss.dauer);
      element("ergebnis-grund").textContent = abschlussText(
        wert.abschluss.endgrund,
        this.personaName,
      );
      element("ergebnis-felder").textContent =
        `${String(this.notizen.ausgefuellt(this.kriterien))} von ${String(this.kriterien.length)}`;
    }
    if (wechsel) {
      const fokus: Record<Phase, string> = {
        bereit: "start",
        mikrofon_anfrage: "mikrofon-titel",
        briefing: "briefing-titel",
        anwaehlen: "anwaehlen-titel",
        gespraech: "gespraech-titel",
        ausfuellen: "abschluss-titel",
        scoreboard: "ergebnis-titel",
      };
      element(fokus[wert.phase]).focus();
    }
  }
}
