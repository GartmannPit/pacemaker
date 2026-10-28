import type { Phase, Rolle, Zustand } from "./gespraech.ts";

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
    this.ansicht("bereit");
    element("nutzer").textContent = name;
    element("abmelden").hidden = false;
    element("transkript-knopf").hidden = true;
    this.status("Bereit für Ihr Gespräch.");
    this.fokus("bereit-titel");
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
    this.zeile = null;
    this.deltaSprecher = null;
    this.sprecher = null;
    this.deltaZeit = 0;
    this.pegelZeit = 0;
    element("transkript-inhalt").replaceChildren();
    const leer = document.createElement("p");
    leer.className = "klein";
    leer.id = "transkript-leer";
    leer.textContent = "Sobald Sie oder Brandt sprechen, erscheint hier das Transkript.";
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
      name.textContent = rolle === "sie" ? "Sie" : "Brandt";
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
        ? "Markus Brandt spricht"
        : rolle === "sie"
          ? "Sie sprechen"
          : "Verbunden · Gesprächspause";
    element("sprecher").textContent = text;
    element("cue-text").textContent =
      rolle === "brandt" ? "Brandt spricht" : rolle === "sie" ? "Sie sprechen" : "Verbunden";
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
