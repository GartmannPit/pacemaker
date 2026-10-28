import { ApiFehler, fehlermeldung } from "./api.ts";
import type { StartAntwort } from "./api.ts";
import { herzschlagStarten, systemUhr } from "./herzschlag.ts";
import type { EndeGrund, HerzEnde, Uhr } from "./herzschlag.ts";

export type Rolle = "sie" | "brandt";
export type Phase = "bereit" | "verbindet" | "gespraech" | "beendet";
export interface Zustand {
  phase: Phase;
  meldung: string;
  start: number | null;
  maxDauer: number;
  dauer: number;
}
export interface Mikrofon {
  getTracks(): { stop(): void }[];
}
export interface Analyse {
  mikrofon(stream: MediaStream): void;
  remote(stream: MediaStream): void;
  stop(): void;
}
export interface Verbindung {
  angebot(signal: AbortSignal): Promise<string>;
  antwort(sdp: string): Promise<void>;
  stop(): void;
}
export interface Ports<Stream extends Mikrofon> {
  uhr: Uhr;
  analyse(): Analyse;
  mikrofon(): Promise<Stream>;
  peer(
    stream: Stream,
    analyse: Analyse,
    callbacks: {
      transkript(rolle: Rolle, delta: string): void;
      verbindung(zustand: string): void;
    },
  ): Verbindung;
  starten(sdp: string): Promise<StartAntwort>;
  beenden(ref: string): Promise<unknown>;
  personaName?(): string;
  herz(ref: string, ende: (ereignis: HerzEnde) => void): () => void;
  beacon(ref: string): void;
  zustand(wert: Zustand): void;
  leeren(): void;
  transkript(rolle: Rolle, delta: string): void;
  abgemeldet(meldung: string): void;
}
interface Kontext<Stream extends Mikrofon> {
  generation: number;
  ctrl: AbortController;
  analyse: Analyse;
  mic: Stream | null;
  peer: Verbindung | null;
  ref: string | null;
  verbunden: boolean;
  herzStop: () => void;
  verbindungStop: () => void;
}

export function abschlusstext(grund: EndeGrund | null, personaName = "Ihr Gegenüber"): string {
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

// DOM-freier Zustandsautomat. Ausschließlich der aktuelle Kontext darf die Ansicht
// oder Ressourcen ändern. Lokales Aufräumen wartet niemals auf einen HTTP-Aufruf.
export class Gespraech<Stream extends Mikrofon> {
  private readonly ports: Ports<Stream>;
  private generation = 0;
  private kontext: Kontext<Stream> | null = null;
  private wert: Zustand = {
    phase: "bereit",
    meldung: "Bereit.",
    start: null,
    maxDauer: 0,
    dauer: 0,
  };

  constructor(ports: Ports<Stream>) {
    this.ports = ports;
  }

  private aktuell(k: Kontext<Stream>): boolean {
    return this.kontext === k && !k.ctrl.signal.aborted;
  }
  private anzeigen(wert: Zustand) {
    this.wert = wert;
    this.ports.zustand(wert);
  }

  private aufraeumen() {
    const k = this.kontext;
    this.kontext = null;
    if (!k) return;
    k.ctrl.abort();
    k.herzStop();
    k.verbindungStop();
    k.mic?.getTracks().forEach((track) => {
      track.stop();
    });
    k.peer?.stop();
    k.mic = null;
    k.peer = null;
    try {
      k.analyse.stop();
    } catch {
      /* Die Audioressourcen sind bereits gestoppt. */
    }
  }
  private endeSenden(ref: string, generation = this.generation) {
    void this.ports.beenden(ref).catch((fehler: unknown) => {
      if (generation === this.generation && fehler instanceof ApiFehler && fehler.status === 401) {
        this.abmelden();
        this.ports.abgemeldet(fehler.message);
      }
    });
  }
  private abschliessen(k: Kontext<Stream>, meldung: string, senden: boolean) {
    if (!this.aktuell(k)) return;
    const ref = k.ref;
    const dauer =
      this.wert.start === null ? 0 : Math.max(0, this.ports.uhr.jetzt() - this.wert.start);
    this.aufraeumen();
    this.anzeigen({ ...this.wert, phase: "beendet", meldung, dauer });
    if (ref && senden) this.endeSenden(ref);
  }

  async starten(): Promise<void> {
    if (this.kontext) return;
    this.generation++;
    this.ports.leeren();
    const k: Kontext<Stream> = {
      generation: this.generation,
      ctrl: new AbortController(),
      analyse: { mikrofon() {}, remote() {}, stop() {} },
      mic: null,
      peer: null,
      ref: null,
      verbunden: false,
      herzStop: () => {},
      verbindungStop: () => {},
    };
    this.kontext = k;
    try {
      k.analyse = this.ports.analyse();
    } catch {
      /* Die Pegelanzeige ist optional. */
    }
    this.anzeigen({
      phase: "verbindet",
      meldung: "Mikrofon freigeben und verbinden …",
      start: null,
      maxDauer: 0,
      dauer: 0,
    });
    try {
      const stream = await this.ports.mikrofon();
      if (!this.aktuell(k)) {
        stream.getTracks().forEach((track) => {
          track.stop();
        });
        return;
      }
      k.mic = stream;
      k.peer = this.ports.peer(stream, k.analyse, {
        transkript: (rolle, delta) => {
          if (this.aktuell(k)) this.ports.transkript(rolle, delta);
        },
        verbindung: (zustand) => {
          if (!this.aktuell(k)) return;
          if (zustand === "failed")
            this.abschliessen(k, abschlusstext("verbindung_verloren"), true);
          else if (zustand === "disconnected") {
            k.verbindungStop();
            k.verbindungStop = this.ports.uhr.setzen(() => {
              this.abschliessen(k, abschlusstext("verbindung_verloren"), true);
            }, 5000);
          } else if (zustand === "connected" || zustand === "completed") {
            k.verbindungStop();
            k.verbunden = true;
            if (k.ref && this.wert.phase !== "gespraech")
              this.anzeigen({
                ...this.wert,
                phase: "gespraech",
                meldung: "Verbunden. Sie können sprechen.",
              });
          }
        },
      });
      const sdp = await k.peer.angebot(k.ctrl.signal);
      if (!this.aktuell(k)) return;
      // Nicht durch Abbrechen verschlucken: eine späte erfolgreiche Startantwort
      // enthält die Referenz, die wir zum gezielten Schließen benötigen.
      const antwort = await this.ports.starten(sdp);
      if (!this.aktuell(k)) {
        this.endeSenden(antwort.session_ref, k.generation);
        return;
      }
      k.ref = antwort.session_ref;
      const start = this.ports.uhr.jetzt();
      this.anzeigen({
        ...this.wert,
        start,
        maxDauer: antwort.max_dauer_s,
        meldung: "Die Gesprächsverbindung wird hergestellt …",
      });
      k.verbindungStop = this.ports.uhr.setzen(() => {
        this.abschliessen(
          k,
          "Die Gesprächsverbindung konnte nicht hergestellt werden. Bitte starten Sie erneut.",
          true,
        );
      }, 15000);
      k.herzStop = this.ports.herz(k.ref, (ereignis) => {
        if (!this.aktuell(k)) return;
        if (ereignis.art === "anmeldung") {
          this.abmelden();
          this.ports.abgemeldet("Bitte melden Sie sich erneut an.");
        } else {
          this.abschliessen(
            k,
            ereignis.art === "frist"
              ? "Der Server ist nicht mehr erreichbar. Das Gespräch wurde lokal beendet. Bitte prüfen Sie Ihre Verbindung."
              : abschlusstext(ereignis.grund, this.ports.personaName?.()),
            ereignis.art === "frist",
          );
        }
      });
      await k.peer.antwort(antwort.sdp);
      if (!this.aktuell(k)) return;
      if (k.verbunden && this.wert.phase !== "gespraech")
        this.anzeigen({
          ...this.wert,
          phase: "gespraech",
          meldung: "Verbunden. Sie können sprechen.",
        });
    } catch (fehler) {
      if (!this.aktuell(k)) return;
      if (fehler instanceof ApiFehler && fehler.status === 401) {
        this.abmelden();
        this.ports.abgemeldet(fehler.message);
      } else this.abschliessen(k, fehlermeldung(fehler), true);
    }
  }

  beenden() {
    if (this.kontext)
      this.abschliessen(
        this.kontext,
        this.wert.phase === "verbindet"
          ? "Sie haben den Verbindungsaufbau abgebrochen."
          : abschlusstext("nutzer"),
        true,
      );
  }
  abmelden() {
    this.generation++;
    const ref = this.kontext?.ref;
    this.aufraeumen();
    this.ports.leeren();
    this.wert = { phase: "bereit", meldung: "Bereit.", start: null, maxDauer: 0, dauer: 0 };
    if (ref) this.endeSenden(ref);
  }
  verlassen() {
    this.generation++;
    const ref = this.kontext?.ref;
    try {
      if (ref) this.ports.beacon(ref);
    } catch {
      /* Ein abgewiesener Beacon darf das lokale Aufräumen nicht verhindern. */
    }
    this.aufraeumen();
    this.ports.leeren();
  }
}

export function browserVerbindung(
  stream: MediaStream,
  analyse: Analyse,
  audio: HTMLAudioElement,
  callbacks: {
    transkript(rolle: Rolle, delta: string): void;
    verbindung(zustand: string): void;
    tonBlockiert(blockiert: boolean): void;
  },
): Verbindung {
  const peer = new RTCPeerConnection();
  let aktiv = true;
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
    audio.srcObject = remote;
    analyse.remote(remote);
    void audio.play().then(
      () => {
        if (aktiv) callbacks.tonBlockiert(false);
      },
      () => {
        if (aktiv) callbacks.tonBlockiert(true);
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
