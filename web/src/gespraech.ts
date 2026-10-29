import { ApiFehler, fehlermeldung } from "./api.ts";
import type { StartAntwort, Messung } from "./api.ts";
import { herzschlagStarten, systemUhr, serverGrund } from "./herzschlag.ts";
import type { EndeGrund, HerzEnde, Uhr } from "./herzschlag.ts";
import { Countdown } from "./countdown.ts";

export type Rolle = "sie" | "brandt";
export type Phase =
  | "bereit"
  | "mikrofon_anfrage"
  | "briefing"
  | "anwaehlen"
  | "gespraech"
  | "ausfuellen"
  | "scoreboard";
export type BeginnSignal = "audio" | "transkript" | "frist";
export type AbschlussGrund =
  | { art: "server"; grund: EndeGrund | "unbekannt" }
  | {
      art: "lokal";
      grund: "nutzer" | "verbindung_verloren" | "herzschlagfrist" | "steuerungsfehler";
    };
export interface Abschluss {
  beginn: number;
  ende: number;
  dauer: number;
  signal: BeginnSignal;
  endgrund: AbschlussGrund;
}
export interface Zustand {
  phase: Phase;
  meldung: string;
  start: number | null;
  maxDauer: number;
  restzeit: number | null;
  countdown: number | null;
  pausiert: boolean;
  tonBlockiert: boolean;
  abschluss: Abschluss | null;
}
export interface Mikrofon {
  getTracks(): { enabled: boolean; stop(): void }[];
}
export interface Analyse {
  mikrofon(stream: MediaStream): void;
  remote(stream: MediaStream): void;
  stop(): void;
}
export interface AnrufAudio extends Analyse {
  laeuft(): boolean;
  freigeben(): Promise<boolean>;
  detektor(): boolean;
  waehlen(): void;
  ruhe(): void;
}
export interface Verbindung {
  angebot(signal: AbortSignal): Promise<string>;
  antwort(sdp: string): Promise<void>;
  freigeben(): Promise<boolean>;
  stop(): void;
}
export interface Ports<Stream extends Mikrofon> {
  uhr: Uhr;
  analyse(audio: () => void, aenderung: () => void): AnrufAudio;
  mikrofon(): Promise<Stream>;
  peer(
    stream: Stream,
    analyse: Analyse,
    callbacks: {
      transkript(rolle: Rolle, delta: string): void;
      verbindung(zustand: string): void;
      wiedergabe(frei: boolean): void;
    },
  ): Verbindung;
  starten(sdp: string, framework: string): Promise<StartAntwort>;
  bereit(ref: string): Promise<unknown>;
  messung(ref: string, messung: Messung): Promise<unknown>;
  beenden(ref: string, messung?: Messung): Promise<unknown>;
  personaName?(): string;
  herz(ref: string, ende: (ereignis: HerzEnde) => void): () => void;
  beacon(ref: string, messung?: Messung): void;
  zustand(wert: Zustand): void;
  ansage(text: string): void;
  leeren(): void;
  transkript(rolle: Rolle, delta: string): void;
  abgemeldet(meldung: string): void;
}
interface Kontext<Stream extends Mikrofon> {
  generation: number;
  ctrl: AbortController;
  analyse: AnrufAudio;
  mic: Stream | null;
  peer: Verbindung | null;
  ref: string | null;
  framework: string;
  verbunden: boolean;
  wiedergabe: boolean;
  c: number | null;
  bereit: number | null;
  audio: number | null;
  transkript: number | null;
  beginn: number | null;
  signal: BeginnSignal;
  sitzungsStart: number | null;
  timer: Map<string, () => void>;
}
const leeresAudio = (): AnrufAudio => ({
  mikrofon() {},
  remote() {},
  stop() {},
  laeuft: () => false,
  freigeben: () => Promise.resolve(false),
  detektor: () => false,
  waehlen() {},
  ruhe() {},
});
function anfang(meldung = "Bereit."): Zustand {
  return {
    phase: "bereit",
    meldung,
    start: null,
    maxDauer: 0,
    restzeit: null,
    countdown: null,
    pausiert: false,
    tonBlockiert: false,
    abschluss: null,
  };
}
export function abschlussText(grund: AbschlussGrund, name?: string): string {
  if (grund.art === "server") return abschlusstext(grund.grund, name);
  switch (grund.grund) {
    case "nutzer":
      return "Sie haben das Gespräch lokal beendet. Der Abschluss beim Anbieter ist nicht bestätigt.";
    case "herzschlagfrist":
      return "Der Server ist nicht mehr erreichbar. Das Gespräch wurde lokal beendet. Bitte prüfen Sie Ihre Verbindung.";
    case "verbindung_verloren":
      return "Die Verbindung wurde unterbrochen. Das Gespräch wurde lokal beendet.";
    case "steuerungsfehler":
      return "Die Gesprächssteuerung ist nicht erreichbar. Das Gespräch wurde lokal beendet.";
  }
}
export function abschlusstext(
  grund: EndeGrund | "unbekannt" | null,
  personaName = "Ihr Gegenüber",
): string {
  switch (grund) {
    case "nutzer":
      return "Sie haben das Gespräch beendet.";
    case "auflegen":
      return `${personaName} hat aufgelegt. Das Gespräch ist beendet.`;
    case "zeitlimit":
      return "Die vorgesehene Gesprächszeit ist abgelaufen.";
    case "inaktiv":
      return "Das Gespräch wurde wegen längerer Inaktivität beendet.";
    case "tab_geschlossen":
      return "Das Gespräch wurde beim Verlassen der Seite beendet.";
    case "verbindung_verloren":
      return "Die Gesprächsverbindung wurde unterbrochen. Bitte starten Sie erneut.";
    case "herzschlag_fehlt":
      return "Der Server hat keine Lebenszeichen mehr erhalten. Bitte prüfen Sie Ihre Verbindung.";
    case "wiederanlauf":
      return "Der Server wurde neu gestartet. Bitte starten Sie ein neues Gespräch.";
    case "sideband_abbruch":
    case "attach_fehler":
      return "Die Gesprächssteuerung wurde unterbrochen. Bitte starten Sie erneut.";
    case "server_ende":
      return "Der Server hat das Gespräch beendet. Sie können ein neues Gespräch starten.";
    default:
      return "Das Gespräch ist beendet oder beim Server nicht mehr verfügbar.";
  }
}

// DOM-freier Ablauf; jede verzögerte Arbeit gehört zu genau einer Generation.
export class Gespraech<Stream extends Mikrofon> {
  private readonly ports: Ports<Stream>;
  private generation = 0;
  private kontext: Kontext<Stream> | null = null;
  private countdown: Countdown | null = null;
  private wert = anfang();
  constructor(ports: Ports<Stream>) {
    this.ports = ports;
  }
  private aktuell(k: Kontext<Stream>) {
    return this.kontext === k && !k.ctrl.signal.aborted;
  }
  private anzeigen(wert: Zustand) {
    this.wert = wert;
    this.ports.zustand(wert);
  }
  private timer(k: Kontext<Stream>, name: string, ms: number, aufgabe: () => void) {
    k.timer.get(name)?.();
    k.timer.set(
      name,
      this.ports.uhr.setzen(() => {
        k.timer.delete(name);
        if (this.aktuell(k)) aufgabe();
      }, ms),
    );
  }
  private timerStop(k: Kontext<Stream>, name: string) {
    k.timer.get(name)?.();
    k.timer.delete(name);
  }
  private aufraeumen() {
    this.countdown?.stop();
    this.countdown = null;
    const k = this.kontext;
    this.kontext = null;
    if (!k) return;
    k.ctrl.abort();
    for (const stop of k.timer.values()) stop();
    k.timer.clear();
    const freigaben = [
      ...(k.mic?.getTracks().map((t) => () => {
        t.stop();
      }) ?? []),
      () => {
        k.peer?.stop();
      },
      () => {
        k.analyse.stop();
      },
    ];
    for (const freigeben of freigaben) {
      try {
        freigeben();
      } catch {
        /* Die übrigen Ressourcen trotzdem freigeben. */
      }
    }
    k.mic = null;
    k.peer = null;
  }
  private auth(fehler: unknown, generation: number): boolean {
    if (generation !== this.generation || !(fehler instanceof ApiFehler) || fehler.status !== 401)
      return false;
    this.abmelden();
    this.ports.abgemeldet(fehler.message);
    return true;
  }
  private endeSenden(ref: string, generation: number, messung?: Messung) {
    void this.ports.beenden(ref, messung).catch((f: unknown) => {
      this.auth(f, generation);
    });
  }
  private messwerte(k: Kontext<Stream>, status: Messung["status"]): Messung {
    const differenz = (ende: number | null, start: number | null) =>
      ende === null || start === null
        ? null
        : Math.min(600000, Math.max(0, Math.round(ende - start)));
    return {
      status,
      c_bis_audio_ms: differenz(k.audio, k.c),
      bereit_bis_audio_ms: differenz(k.audio, k.bereit),
      c_bis_transkript_ms: differenz(k.transkript, k.c),
    };
  }
  private abschliessen(
    k: Kontext<Stream>,
    grund: AbschlussGrund,
    senden: boolean,
    meldung = abschlussText(grund, this.ports.personaName?.()),
  ) {
    if (!this.aktuell(k)) return;
    const messung =
      this.wert.phase === "anwaehlen"
        ? this.messwerte(
            k,
            grund.art === "lokal" && grund.grund === "nutzer" ? "abbruch" : "fehler",
          )
        : undefined;
    const ende = this.ports.uhr.jetzt();
    const abschluss: Abschluss | null =
      k.beginn === null
        ? null
        : {
            beginn: k.beginn,
            ende,
            dauer: Math.max(0, ende - k.beginn),
            signal: k.signal,
            endgrund: grund,
          };
    const ref = k.ref;
    this.aufraeumen();
    if (abschluss)
      this.anzeigen({ ...this.wert, phase: "ausfuellen", meldung, abschluss, tonBlockiert: false });
    else {
      this.ports.leeren();
      this.anzeigen(anfang(meldung));
    }
    if (ref && senden) this.endeSenden(ref, k.generation, messung);
  }
  private fehler(k: Kontext<Stream>, fehler: unknown) {
    if (!this.aktuell(k)) return;
    if (!this.auth(fehler, k.generation))
      this.abschliessen(
        k,
        { art: "lokal", grund: "steuerungsfehler" },
        true,
        fehlermeldung(fehler),
      );
  }
  async starten(framework: string): Promise<void> {
    if (this.kontext || this.wert.phase !== "bereit") return;
    this.generation++;
    this.ports.leeren();
    const k: Kontext<Stream> = {
      generation: this.generation,
      ctrl: new AbortController(),
      analyse: leeresAudio(),
      mic: null,
      peer: null,
      ref: null,
      framework,
      verbunden: false,
      wiedergabe: false,
      c: null,
      bereit: null,
      audio: null,
      transkript: null,
      beginn: null,
      signal: "frist",
      sitzungsStart: null,
      timer: new Map(),
    };
    this.kontext = k;
    // Erzeugung und resume() synchron in der Startgeste, vor getUserMedia.
    try {
      k.analyse = this.ports.analyse(
        () => {
          if (!this.aktuell(k) || k.bereit === null || this.wert.phase !== "anwaehlen") return;
          k.audio ??= this.ports.uhr.jetzt();
          this.gespraechBeginnen(k, "audio");
        },
        () => {
          if (!this.aktuell(k)) return;
          if (!k.analyse.laeuft() && ["anwaehlen", "gespraech"].includes(this.wert.phase))
            this.tonSperren(k);
          else this.bereitPruefen(k);
        },
      );
    } catch {
      /* Ohne AudioContext ist eine manuelle Freigabe nötig. */
    }
    this.anzeigen({ ...anfang("Bitte geben Sie Ihr Mikrofon frei."), phase: "mikrofon_anfrage" });
    try {
      const stream = await this.ports.mikrofon();
      if (!this.aktuell(k)) {
        stream.getTracks().forEach((t) => {
          t.stop();
        });
        return;
      }
      k.mic = stream;
      this.anzeigen({
        ...this.wert,
        phase: "briefing",
        meldung: "Lesen Sie Ihr Briefing. Es besteht noch keine Verbindung.",
      });
      this.countdownStarten(
        "briefing",
        20,
        () => {
          void this.anwaehlen(k);
        },
        () => {
          this.abschliessen(
            k,
            { art: "lokal", grund: "nutzer" },
            false,
            "Das Briefing war länger als 5 Minuten angehalten. Ihr Mikrofon wurde freigegeben. Bitte starten Sie erneut.",
          );
        },
      );
    } catch (f) {
      this.fehler(k, f);
    }
  }
  private countdownStarten(
    phase: "briefing" | "scoreboard",
    sekunden: number,
    fertig: () => void,
    pauseFrist?: () => void,
  ) {
    this.countdown?.stop();
    this.countdown = new Countdown(
      this.ports.uhr,
      sekunden,
      (rest, pausiert, ansage) => {
        if (this.wert.phase !== phase) return;
        this.anzeigen({ ...this.wert, countdown: rest, pausiert });
        if (ansage)
          this.ports.ansage(
            phase === "briefing"
              ? `Briefing, Anruf startet in ${String(rest)} Sekunden.`
              : `Ergebnis, schließt in ${String(rest)} Sekunden.`,
          );
      },
      fertig,
      pauseFrist,
    );
  }
  pause() {
    this.countdown?.umschalten();
  }
  ueberspringen() {
    if (this.wert.phase === "briefing" && this.kontext) void this.anwaehlen(this.kontext);
    else if (this.wert.phase === "scoreboard") this.zurueck();
  }
  fertig() {
    if (this.wert.phase !== "ausfuellen") return;
    this.anzeigen({ ...this.wert, phase: "scoreboard", meldung: "Ihr Gesprächsergebnis." });
    this.countdownStarten("scoreboard", 10, () => {
      this.zurueck();
    });
  }
  private zurueck() {
    this.aufraeumen();
    this.ports.leeren();
    this.anzeigen(anfang());
  }
  private async anwaehlen(k: Kontext<Stream>): Promise<void> {
    if (!this.aktuell(k) || this.wert.phase !== "briefing" || !k.mic) return;
    this.countdown?.stop();
    this.countdown = null;
    k.c = this.ports.uhr.jetzt();
    k.mic.getTracks().forEach((t) => {
      t.enabled = false;
    });
    this.anzeigen({
      ...this.wert,
      phase: "anwaehlen",
      countdown: null,
      pausiert: false,
      meldung: "Ihr Gegenüber wird angewählt …",
    });
    try {
      k.analyse.waehlen();
      if (!k.analyse.laeuft()) this.tonSperren(k);
      k.peer = this.ports.peer(k.mic, k.analyse, {
        transkript: (rolle, delta) => {
          if (!this.aktuell(k)) return;
          if (rolle === "brandt" && delta.length > 0) {
            k.transkript ??= this.ports.uhr.jetzt();
            this.ersatzPruefen(k);
          }
          this.ports.transkript(rolle, delta);
        },
        wiedergabe: (frei) => {
          if (!this.aktuell(k)) return;
          k.wiedergabe = frei;
          if (!frei || !k.analyse.laeuft()) this.tonSperren(k);
          else this.bereitPruefen(k);
        },
        verbindung: (status) => {
          if (!this.aktuell(k)) return;
          if (status === "failed")
            this.abschliessen(k, { art: "lokal", grund: "verbindung_verloren" }, true);
          else if (status === "disconnected") {
            k.verbunden = false;
            this.timer(k, "verbindung", 5000, () => {
              this.abschliessen(k, { art: "lokal", grund: "verbindung_verloren" }, true);
            });
          } else if (status === "connected" || status === "completed") {
            this.timerStop(k, "verbindung");
            k.verbunden = true;
            this.bereitPruefen(k);
          }
        },
      });
      const sdp = await k.peer.angebot(k.ctrl.signal);
      if (!this.aktuell(k)) return;
      // Start nicht abbrechen: eine späte erfolgreiche Antwort gezielt schließen.
      const antwort = await this.ports.starten(sdp, k.framework);
      if (!this.aktuell(k)) {
        this.endeSenden(antwort.session_ref, k.generation, this.messwerte(k, "abbruch"));
        return;
      }
      k.ref = antwort.session_ref;
      k.sitzungsStart = this.ports.uhr.jetzt();
      this.anzeigen({
        ...this.wert,
        maxDauer: antwort.max_dauer_s,
        restzeit: antwort.max_dauer_s * 1000,
      });
      if (!k.verbunden)
        this.timer(k, "verbindung", 15000, () => {
          this.abschliessen(
            k,
            { art: "lokal", grund: "verbindung_verloren" },
            true,
            "Die Gesprächsverbindung konnte nicht hergestellt werden. Bitte starten Sie erneut.",
          );
        });
      const stop = this.ports.herz(k.ref, (ereignis) => {
        this.herzEnde(k, ereignis);
      });
      if (!this.aktuell(k)) {
        stop();
        return;
      }
      k.timer.set("herz", stop);
      await k.peer.antwort(antwort.sdp);
      if (this.aktuell(k)) this.bereitPruefen(k);
    } catch (f) {
      this.fehler(k, f);
    }
  }
  private herzEnde(k: Kontext<Stream>, e: HerzEnde) {
    if (!this.aktuell(k)) return;
    if (e.art === "anmeldung") {
      this.abmelden();
      this.ports.abgemeldet("Bitte melden Sie sich erneut an.");
    } else if (e.art === "frist")
      this.abschliessen(k, { art: "lokal", grund: "herzschlagfrist" }, true);
    else this.abschliessen(k, { art: "server", grund: serverGrund(e.grund) }, false);
  }
  private tonSperren(k: Kontext<Stream>) {
    this.anzeigen({ ...this.wert, tonBlockiert: true });
    if (this.wert.phase === "anwaehlen" && !k.timer.has("ton"))
      this.timer(k, "ton", 30000, () => {
        this.abschliessen(
          k,
          { art: "lokal", grund: "nutzer" },
          true,
          "Der Ton wurde nicht rechtzeitig freigegeben. Bitte starten Sie erneut und wählen Sie „Ton aktivieren“.",
        );
      });
  }
  async tonAktivieren() {
    const k = this.kontext;
    if (!k || !["anwaehlen", "gespraech"].includes(this.wert.phase)) return;
    // Beide Aufrufe bleiben innerhalb der Nutzergeste.
    const context = k.analyse.freigeben();
    const wiedergabe = k.peer?.freigeben() ?? Promise.resolve(false);
    try {
      const [laeuft, frei] = await Promise.all([context, wiedergabe]);
      if (!this.aktuell(k)) return;
      k.wiedergabe = frei;
      if (laeuft && frei) {
        this.anzeigen({ ...this.wert, tonBlockiert: false });
        this.bereitPruefen(k);
      } else this.tonSperren(k);
    } catch {
      if (this.aktuell(k)) this.tonSperren(k);
    }
  }
  private bereitPruefen(k: Kontext<Stream>) {
    if (!this.aktuell(k) || !k.wiedergabe || !k.analyse.laeuft()) return;
    this.timerStop(k, "ton");
    if (this.wert.tonBlockiert) this.anzeigen({ ...this.wert, tonBlockiert: false });
    if (!k.verbunden || !k.ref || this.wert.phase !== "anwaehlen") return;
    if (k.bereit !== null) {
      if (k.audio !== null) this.gespraechBeginnen(k, "audio");
      this.ersatzPruefen(k);
      if (k.beginn === null && this.ports.uhr.jetzt() - k.bereit >= 15000)
        this.gespraechBeginnen(k, "frist");
      return;
    }
    k.bereit = this.ports.uhr.jetzt();
    this.timer(k, "audio", 15000, () => {
      if (k.verbunden && k.wiedergabe && k.analyse.laeuft()) this.gespraechBeginnen(k, "frist");
    });
    void this.ports.bereit(k.ref).catch((f: unknown) => {
      this.fehler(k, f);
    });
    this.ersatzPruefen(k);
  }
  private ersatzPruefen(k: Kontext<Stream>) {
    if (
      this.wert.phase === "anwaehlen" &&
      k.bereit !== null &&
      k.transkript !== null &&
      !k.analyse.detektor() &&
      k.verbunden &&
      k.wiedergabe &&
      k.analyse.laeuft()
    )
      this.gespraechBeginnen(k, "transkript");
  }
  private gespraechBeginnen(k: Kontext<Stream>, signal: BeginnSignal) {
    if (
      !this.aktuell(k) ||
      this.wert.phase !== "anwaehlen" ||
      !k.verbunden ||
      !k.wiedergabe ||
      !k.analyse.laeuft()
    )
      return;
    this.timerStop(k, "audio");
    k.analyse.ruhe();
    k.beginn =
      (signal === "audio" ? k.audio : signal === "transkript" ? k.transkript : null) ??
      this.ports.uhr.jetzt();
    k.signal = signal;
    k.mic?.getTracks().forEach((t) => {
      t.enabled = true;
    });
    this.anzeigen({
      ...this.wert,
      phase: "gespraech",
      start: k.beginn,
      meldung:
        signal === "frist"
          ? "Ihr Gegenüber ist verbunden, aber still – Sie können sprechen."
          : "Verbunden. Sie können sprechen.",
    });
    if (k.ref)
      void this.ports
        .messung(k.ref, this.messwerte(k, signal === "frist" ? "frist" : "ok"))
        .catch((f: unknown) => {
          this.auth(f, k.generation);
        });
    const tick = () => {
      if (!this.aktuell(k)) return;
      this.anzeigen({
        ...this.wert,
        restzeit: Math.max(
          0,
          this.wert.maxDauer * 1000 - (this.ports.uhr.jetzt() - (k.sitzungsStart ?? 0)),
        ),
      });
      this.timer(k, "restzeit", 250, tick);
    };
    tick();
  }
  beenden() {
    if (this.kontext) this.abschliessen(this.kontext, { art: "lokal", grund: "nutzer" }, true);
  }
  abmelden() {
    const k = this.kontext;
    const messung = k && this.wert.phase === "anwaehlen" ? this.messwerte(k, "abbruch") : undefined;
    this.generation++;
    this.aufraeumen();
    this.ports.leeren();
    this.wert = anfang();
    if (k?.ref) this.endeSenden(k.ref, k.generation, messung);
  }
  verlassen() {
    const k = this.kontext;
    this.generation++;
    try {
      if (k?.ref)
        this.ports.beacon(
          k.ref,
          this.wert.phase === "anwaehlen" ? this.messwerte(k, "abbruch") : undefined,
        );
    } catch {
      /* Lokales Aufräumen bleibt unabhängig vom Beacon. */
    }
    this.aufraeumen();
    this.ports.leeren();
    this.wert = anfang();
  }
}

export function browserVerbindung(
  stream: MediaStream,
  analyse: Analyse,
  audio: HTMLAudioElement,
  callbacks: {
    transkript(rolle: Rolle, delta: string): void;
    verbindung(zustand: string): void;
    wiedergabe(frei: boolean): void;
  },
): Verbindung {
  const peer = new RTCPeerConnection();
  let aktiv = true;
  let remoteVorhanden = false;
  const track = stream.getAudioTracks()[0];
  if (!track) {
    peer.close();
    throw new Error("Kein Audiotrack");
  }
  try {
    peer.addTrack(track, stream);
  } catch (fehler) {
    peer.close();
    throw fehler;
  }
  // Zusätzliche Tracks werden weder gesendet noch offengelassen.
  stream
    .getTracks()
    .filter((t) => t !== track)
    .forEach((t) => {
      t.stop();
    });
  analyse.mikrofon(stream);
  peer.ontrack = (ereignis) => {
    if (!aktiv) return;
    const remote = new MediaStream([ereignis.track]);
    remoteVorhanden = true;
    audio.srcObject = remote;
    analyse.remote(remote);
    // Auch eine unaufgelöste play()-Promise braucht eine begrenzte Freigabefrist.
    callbacks.wiedergabe(false);
    void audio.play().then(
      () => {
        if (aktiv) callbacks.wiedergabe(true);
      },
      () => {
        if (aktiv) callbacks.wiedergabe(false);
      },
    );
  };
  const status = () => {
    if (aktiv)
      callbacks.verbindung(
        peer.iceConnectionState === "failed" || peer.iceConnectionState === "disconnected"
          ? peer.iceConnectionState
          : peer.connectionState,
      );
  };
  peer.onconnectionstatechange = status;
  peer.oniceconnectionstatechange = status;
  let kanal: RTCDataChannel;
  try {
    kanal = peer.createDataChannel("oai-events");
  } catch (fehler) {
    peer.close();
    throw fehler;
  }
  kanal.onmessage = (ereignis: MessageEvent<unknown>) => {
    if (!aktiv || typeof ereignis.data !== "string") return;
    try {
      const wert: unknown = JSON.parse(ereignis.data);
      if (
        !wert ||
        typeof wert !== "object" ||
        !("type" in wert) ||
        !("delta" in wert) ||
        typeof wert.delta !== "string"
      )
        return;
      if (wert.type === "session.input_transcript.delta") callbacks.transkript("sie", wert.delta);
      else if (wert.type === "session.output_transcript.delta")
        callbacks.transkript("brandt", wert.delta);
    } catch {
      /* Nicht freigegebene und ungültige Ereignisse werden nicht übernommen. */
    }
  };
  return {
    async freigeben() {
      if (!aktiv || !remoteVorhanden) return false;
      try {
        await audio.play();
        return aktiv;
      } catch {
        return false;
      }
    },
    async angebot(signal) {
      await peer.setLocalDescription(await peer.createOffer());
      if (signal.aborted) throw new Error("Start abgebrochen");
      if (peer.iceGatheringState !== "complete")
        await new Promise<void>((resolve) => {
          const fertig = () => {
            clearTimeout(timer);
            peer.removeEventListener("icegatheringstatechange", wechsel);
            signal.removeEventListener("abort", fertig);
            resolve();
          };
          const wechsel = () => {
            if (peer.iceGatheringState === "complete") fertig();
          };
          const timer = setTimeout(fertig, 5000);
          peer.addEventListener("icegatheringstatechange", wechsel);
          signal.addEventListener("abort", fertig, { once: true });
        });
      if (abgebrochen(signal) || !peer.localDescription?.sdp) throw new Error("Start abgebrochen");
      return peer.localDescription.sdp;
    },
    async antwort(sdp) {
      await peer.setRemoteDescription({ type: "answer", sdp });
    },
    stop() {
      aktiv = false;
      kanal.onmessage = null;
      kanal.close();
      peer.ontrack = null;
      peer.onconnectionstatechange = null;
      peer.oniceconnectionstatechange = null;
      audio.pause();
      if (audio.srcObject instanceof MediaStream)
        audio.srcObject.getTracks().forEach((t) => {
          t.stop();
        });
      audio.srcObject = null;
      peer.close();
    },
  };
}

export { herzschlagStarten, systemUhr };

function abgebrochen(signal: AbortSignal): boolean {
  return signal.aborted;
}
