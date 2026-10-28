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
  private phase: Phase = "bereit";
  private zustand: Zustand | null = null;
  private zeile: { rolle: Rolle; text: HTMLParagraphElement } | null = null;
  private sprecher: Rolle | null = null;
  private deltaSprecher: Rolle | null = null;
  private deltaZeit = 0;
  private pegelZeit = 0;
  private uhr: ReturnType<typeof setInterval> | null = null;
  private reduziert = matchMedia("(prefers-reduced-motion: reduce)");

  status(meldung: string) {
    element("status").textContent = meldung;
  }
  private fokus(id: string) {
    element(id).focus();
  }
  private ansicht(id: string) {
    for (const name of ["anmeldung", "bereit", "sitzung"]) element(name).hidden = name !== id;
  }
  anmeldung(meldung: string) {
    this.phase = "bereit";
    this.zustand = null;
    this.stop();
    this.leeren();
    this.briefingLeeren();
    element("auswertung-notizen").replaceChildren();
    this.ansicht("anmeldung");
    element("abmelden").hidden = true;
    element("transkript-knopf").hidden = true;
    element("nutzer").textContent = "";
    this.status(meldung);
    this.fokus("anmeldung-titel");
  }
  bereit(name: string) {
    this.phase = "bereit";
    this.zustand = null;
    this.stop();
    this.leeren();
    this.briefingLeeren();
    this.ansicht("bereit");
    element("nutzer").textContent = name;
    element("abmelden").hidden = false;
    element("transkript-knopf").hidden = true;
    this.status("Ihr Briefing wird geladen …");
    this.fokus("bereit-titel");
  }
  private briefingLeeren() {
    this.personaName = "Ihr Gegenüber";
    element("bereit-titel").textContent = "Ihr Briefing wird geladen …";
    element("szene").textContent = "Gesprächstraining mit einer KI-Trainingsfigur";
    element("briefing-inhalt").hidden = true;
    for (const id of [
      "briefing-ziel",
      "briefing-fakten",
      "briefing-dauer",
      "briefing-hinweis",
      "framework-name",
      "framework-quelle",
      "briefing-kriterien",
      "briefing-punkte",
      "persona-name",
      "persona-beschreibung",
      "persona-produkt",
      "gespraech-kriterien",
    ])
      element(id).replaceChildren();
    element("kontingent").hidden = true;
  }
  briefing(daten: Briefing) {
    const modell = briefingModell(daten);
    this.personaName = modell.name;
    element("bereit-titel").textContent = modell.titel;
    element("briefing-ziel").textContent = `Ihr Ziel: ${modell.ziel}`;
    element("szene").textContent = `Probe · Gespräch mit ${modell.name}`;
    element("persona-name").textContent = modell.name;
    element("persona-beschreibung").textContent = modell.beschreibung;
    element("persona-produkt").textContent = `Sie verkaufen ${modell.produkt}.`;
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
    element("kriterien-titel").textContent = `Qualifizierung · ${modell.framework}`;
    element("briefing-kriterien").replaceChildren(
      ...modell.kriterien.map((k) => {
        const zeile = textElement("li", "", "kriterium");
        const inhalt = textElement("div", "");
        inhalt.append(textElement("strong", k.label), textElement("p", k.leitfrage, "klein"));
        zeile.append(
          textElement("span", k.key, "kriterium-key"),
          inhalt,
          textElement("span", k.status, "klein"),
        );
        return zeile;
      }),
    );
    element("briefing-punkte").replaceChildren(...modell.punkte.map((p) => textElement("li", p)));
    element("gespraech-kriterien").replaceChildren(
      ...modell.kriterien.map((k) => {
        const zeile = textElement("li", "");
        zeile.title = `${k.label}: ${k.leitfrage}`;
        zeile.setAttribute("aria-label", `${k.key} · ${k.label}: ${k.gespraechStatus}`);
        zeile.append(textElement("b", k.key), textElement("span", k.gespraechStatus));
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
        feld.name = `notiz-${String(index)}`;
        feld.autocomplete = "off";
        feld.rows = 3;
        feld.setAttribute("aria-describedby", "notizen-hinweis");
        feld.value = this.notizen.lesen(k.key);
        feld.addEventListener("input", () => {
          this.notizen.setzen(k.key, feld.value);
        });
        inhalt.append(label, feld);
        zeile.append(textElement("span", k.key, "kriterium-key"), inhalt);
        return zeile;
      }),
    );
    element("briefing-inhalt").hidden = false;
  }
  gegenueber(): string {
    return this.personaName;
  }
  schublade(offen: boolean) {
    const knopf = element<HTMLButtonElement>("transkript-knopf");
    const drawer = element("transkript");
    const fokusImDrawer = drawer.contains(document.activeElement);
    drawer.hidden = !offen;
    drawer.inert = !offen;
    knopf.setAttribute("aria-expanded", String(offen));
    knopf.textContent = offen ? "Transkript ausblenden" : "Transkript einblenden";
    element("gespraech-layout").classList.toggle("offen", offen);
    if (offen) this.fokus("transkript-titel");
    else if (fokusImDrawer) knopf.focus();
  }
  leeren() {
    this.notizen.leeren();
    for (const feld of element("auswertung-notizen").querySelectorAll("textarea")) feld.value = "";
    this.zeile = null;
    this.deltaSprecher = null;
    this.sprecher = null;
    this.deltaZeit = 0;
    this.pegelZeit = 0;
    element("transkript-inhalt").replaceChildren();
    const leer = document.createElement("p");
    leer.className = "klein";
    leer.id = "transkript-leer";
    leer.textContent = "Sobald Sie oder Ihr Gegenüber sprechen, erscheint hier das Transkript.";
    element("transkript-inhalt").append(leer);
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
    this.deltaZeit = Date.now();
    this.sprecherPruefen();
  }
  pegel(eigen: number, brandt: number) {
    const balken = element("mikrofonpegel").children;
    for (let i = 0; i < balken.length; i++) {
      const balkenEl = balken[i];
      if (balkenEl instanceof HTMLElement)
        balkenEl.style.transform = `scaleY(${String(this.reduziert.matches ? 0.14 : Math.max(0.14, eigen * (0.6 + 0.4 * Math.sin(i + 1))))})`;
    }
    if (eigen > 0.08 || brandt > 0.08) {
      this.pegelZeit = Date.now();
      this.sprecherSetzen(brandt >= eigen ? "brandt" : "sie");
    } else this.sprecherPruefen();
  }
  private sprecherPruefen() {
    if (Date.now() - this.pegelZeit < 500) return;
    this.sprecherSetzen(Date.now() - this.deltaZeit < 1400 ? this.deltaSprecher : null);
  }
  private sprecherSetzen(rolle: Rolle | null) {
    if (this.phase !== "gespraech" || this.sprecher === rolle) return;
    this.sprecher = rolle;
    const text =
      rolle === "brandt"
        ? `${this.personaName} spricht`
        : rolle === "sie"
          ? "Sie sprechen"
          : "Verbunden · Gesprächspause";
    element("sprecher").textContent = text;
    element("cue-text").textContent =
      rolle === "brandt"
        ? `${this.personaName} spricht`
        : rolle === "sie"
          ? "Sie sprechen"
          : "Verbunden";
    element("cue-licht").className = `cue-licht ${rolle ?? ""}`;
  }
  aktualisieren(wert: Zustand) {
    const wechsel = wert.phase !== this.phase;
    this.phase = wert.phase;
    this.zustand = wert;
    this.ansicht("sitzung");
    this.status(wert.meldung);
    element("transkript-knopf").hidden = false;
    const beendet = wert.phase === "beendet";
    element("sitzung").classList.toggle("ist-beendet", beendet);
    element("buehne").classList.toggle("ist-beendet", beendet);
    element("transkript-titel").textContent = beendet ? "Transkript" : "Live-Transkript";
    element("abschluss").hidden = !beendet;
    element("sprechend").hidden = beendet;
    element("ringe").hidden = beendet;
    element("pegel-schalter").hidden = beendet;
    element("beenden").hidden = beendet;
    element("beenden").textContent = wert.phase === "verbindet" ? "Abbrechen" : "Beenden";
    element("ton").hidden = true;
    if (beendet) {
      this.stop();
      element("abschluss-text").textContent = wert.meldung;
      element("dauer").textContent =
        wert.start === null
          ? "Es wurde kein Gespräch aufgebaut."
          : `Gesprächsdauer: ${zeit(wert.dauer)}`;
      element("cue-text").textContent = "Beendet";
      element("cue-licht").className = "cue-licht";
    } else {
      element("gespraech-titel").textContent =
        wert.phase === "verbindet" ? "Gespräch wird aufgebaut …" : "Ihr Telefongespräch";
      element("sprecher").textContent =
        wert.phase === "verbindet" ? "Bitte warten Sie." : "Verbunden · Gesprächspause";
      element("cue-text").textContent =
        wert.phase === "verbindet" ? "Verbindungsaufbau" : "Verbunden";
      if (this.uhr === null)
        this.uhr = setInterval(() => {
          this.tick();
          this.sprecherPruefen();
        }, 250);
      this.tick();
    }
    if (wechsel) this.fokus(beendet ? "abschluss-titel" : "gespraech-titel");
  }
  private tick() {
    const wert = this.zustand;
    element("restzeit").textContent =
      wert?.start === null || !wert
        ? "–:–"
        : zeit(wert.maxDauer * 1000 - (Date.now() - wert.start));
  }
  stop() {
    if (this.uhr !== null) clearInterval(this.uhr);
    this.uhr = null;
    for (const balken of element("mikrofonpegel").children)
      if (balken instanceof HTMLElement) balken.style.transform = "scaleY(.14)";
  }
}
