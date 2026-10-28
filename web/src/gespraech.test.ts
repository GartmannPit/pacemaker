import { test } from "node:test";
import assert from "node:assert/strict";
import { abschlusstext, Gespraech } from "./gespraech.ts";
import type { Mikrofon, Ports, Zustand } from "./gespraech.ts";
import { ApiFehler, sitzungStarten, sitzungBeenden } from "./api.ts";
import { Notizen } from "./briefing.ts";
import type { StartAntwort } from "./api.ts";
import type { HerzEnde } from "./herzschlag.ts";
import { offen, spuelen, TestUhr } from "./testhilfe.ts";

function aufbau() {
  const notizen = new Notizen();
  const uhr = new TestUhr();
  const zustaende: Zustand[] = [];
  const enden: string[] = [];
  const beacons: string[] = [];
  let tracksGestoppt = 0,
    peerGestoppt = 0,
    analyseGestoppt = 0,
    geleert = 0,
    abgemeldet = 0,
    deltas = 0;
  const stream: Mikrofon = {
    getTracks: () => [
      {
        stop() {
          tracksGestoppt++;
        },
      },
    ],
  };
  let herzEnde: (e: HerzEnde) => void = () => {};
  let verbindung: (zustand: string) => void = () => {};
  let transkript: (rolle: "sie" | "brandt", delta: string) => void = () => {};
  let herzStop = 0;
  const ports: Ports<Mikrofon> = {
    uhr,
    analyse: () => ({
      stop() {
        analyseGestoppt++;
      },
      mikrofon() {},
      remote() {},
    }),
    mikrofon: () => Promise.resolve(stream),
    peer(_stream, _analyse, callbacks) {
      verbindung = callbacks.verbindung.bind(callbacks);
      transkript = callbacks.transkript.bind(callbacks);
      return {
        angebot: () => Promise.resolve("angebot"),
        antwort: () => {
          verbindung("connected");
          return Promise.resolve();
        },
        stop() {
          peerGestoppt++;
        },
      };
    },
    starten: () => Promise.resolve({ session_ref: "eins", sdp: "antwort", max_dauer_s: 600 }),
    beenden: (ref) => {
      enden.push(ref);
      return Promise.resolve();
    },
    herz(_ref, cb) {
      herzEnde = cb;
      return () => {
        herzStop++;
      };
    },
    beacon(ref) {
      beacons.push(ref);
    },
    zustand(wert) {
      zustaende.push(wert);
    },
    leeren() {
      notizen.leeren();
      geleert++;
    },
    transkript() {
      deltas++;
    },
    abgemeldet() {
      abgemeldet++;
    },
  };
  const g = new Gespraech(ports);
  return {
    notizen,
    g,
    ports,
    uhr,
    stream,
    zustaende,
    enden,
    beacons,
    ende: (e: HerzEnde) => {
      herzEnde(e);
    },
    verbindung: (z: string) => {
      verbindung(z);
    },
    delta: () => {
      transkript("sie", "Synthetischer Text");
    },
    zaehler: () => ({
      tracksGestoppt,
      peerGestoppt,
      analyseGestoppt,
      geleert,
      abgemeldet,
      deltas,
      herzStop,
    }),
  };
}
void test("Beenden stoppt alle Ressourcen sofort trotz hängendem /api/end", async () => {
  const t = aufbau();
  t.ports.beenden = () => offen<unknown>().promise;
  await t.g.starten();
  assert.equal(t.zustaende.at(-1)?.phase, "gespraech");
  await t.uhr.weiter(2000);
  t.g.beenden();
  assert.equal(t.zustaende.at(-1)?.phase, "beendet");
  assert.equal(t.zustaende.at(-1)?.dauer, 2000);
  assert.deepEqual(t.zaehler(), {
    tracksGestoppt: 1,
    peerGestoppt: 1,
    analyseGestoppt: 1,
    geleert: 1,
    abgemeldet: 0,
    deltas: 0,
    herzStop: 1,
  });
});
void test("Start abbrechen vor Mikrofonfreigabe; verspätetes getUserMedia stoppt alte Tracks", async () => {
  const t = aufbau();
  const pending = offen<Mikrofon>();
  t.ports.mikrofon = () => pending.promise;
  const alt = t.g.starten();
  t.g.beenden();
  t.ports.mikrofon = () => Promise.resolve(t.stream);
  await t.g.starten();
  const aktuell = t.zustaende.at(-1);
  pending.loesen(t.stream);
  await alt;
  assert.equal(t.zaehler().tracksGestoppt, 1);
  assert.equal(t.zaehler().peerGestoppt, 0);
  assert.equal(t.zustaende.at(-1), aktuell);
  t.g.abmelden();
});
void test("Späte Startantwort schließt nur alte Sitzung und verändert neues Gespräch nicht", async () => {
  const t = aufbau();
  const pending = offen<StartAntwort>();
  t.ports.starten = () => pending.promise;
  const alt = t.g.starten();
  await spuelen();
  t.g.beenden();
  t.ports.starten = () => Promise.resolve({ session_ref: "neu", sdp: "sdp", max_dauer_s: 120 });
  await t.g.starten();
  const aktuell = t.zustaende.at(-1);
  pending.loesen({ session_ref: "alt", sdp: "sdp", max_dauer_s: 600 });
  await alt;
  assert.deepEqual(t.enden, ["alt"]);
  assert.equal(t.zustaende.at(-1), aktuell);
  t.g.abmelden();
});
void test("Alte Peer- und Herzschlag-Ereignisse wirken nach Neustart nicht", async () => {
  const t = aufbau();
  await t.g.starten();

  // Direkt die gebundenen Callbacks sichern, bevor Ports sie neu belegen.
  let altHerz: (e: HerzEnde) => void = () => {};
  let altPeer: (z: string) => void = () => {};
  const herz = t.ports.herz.bind(t.ports);
  const peer = t.ports.peer.bind(t.ports);
  t.g.beenden();
  t.ports.herz = (ref, cb) => {
    altHerz = cb;
    return herz(ref, cb);
  };
  t.ports.peer = (s, a, cb) => {
    altPeer = cb.verbindung.bind(cb);
    return peer(s, a, cb);
  };
  await t.g.starten();
  t.g.beenden();
  t.ports.herz = herz;
  t.ports.peer = peer;
  await t.g.starten();
  const aktuell = t.zustaende.at(-1);
  altHerz({ art: "anmeldung" });
  altPeer("failed");
  assert.equal(t.zustaende.at(-1), aktuell);
  assert.equal(t.zaehler().abgemeldet, 0);
  t.g.abmelden();
});
void test("Abmelden stoppt sofort und löscht das Transkript; 401 führt zur Anmeldung", async () => {
  const t = aufbau();
  await t.g.starten();
  t.delta();
  t.notizen.setzen("B", "Flüchtige synthetische Notiz");
  t.ende({ art: "anmeldung" });
  assert.equal(t.notizen.lesen("B"), "");
  assert.equal(t.zaehler().abgemeldet, 1);
  assert.equal(t.zaehler().geleert, 2);
  assert.equal(t.zaehler().tracksGestoppt, 1);
  t.delta();
  assert.equal(t.zaehler().deltas, 1);
});
void test("Serverende bewahrt Transkript, liefert Abschlusstext und beendet lokal", async () => {
  const t = aufbau();
  await t.g.starten();
  t.delta();
  t.ende({ art: "ende", grund: "auflegen" });
  assert.match(t.zustaende.at(-1)?.meldung ?? "", /aufgelegt/u);
  assert.equal(t.zaehler().geleert, 1);
  assert.equal(t.zaehler().tracksGestoppt, 1);
  assert.deepEqual(t.enden, []);
});
void test("Disconnect hat 5 s Schonfrist; Erholung hebt sie auf; failed endet sofort", async () => {
  const t = aufbau();
  await t.g.starten();
  t.verbindung("disconnected");
  await t.uhr.weiter(4999);
  assert.equal(t.zustaende.at(-1)?.phase, "gespraech");
  t.verbindung("connected");
  await t.uhr.weiter(1);
  assert.equal(t.zustaende.at(-1)?.phase, "gespraech");
  t.verbindung("failed");
  assert.equal(t.zustaende.at(-1)?.phase, "beendet");
});
void test("Startfehler 401 löscht, anderer Serverfehler zeigt Servermeldung", async () => {
  for (const status of [401, 429]) {
    const t = aufbau();
    t.ports.starten = () => Promise.reject(new ApiFehler("Synthetische Servermeldung", status));
    await t.g.starten();
    assert.equal(t.zaehler().tracksGestoppt, 1);
    if (status === 401) assert.equal(t.zaehler().abgemeldet, 1);
    else assert.equal(t.zustaende.at(-1)?.meldung, "Synthetische Servermeldung");
  }
});
void test("pagehide sendet Beacon und stoppt lokal, auch ohne HTTP-Antwort", async () => {
  const t = aufbau();
  await t.g.starten();
  t.g.verlassen();
  assert.deepEqual(t.beacons, ["eins"]);
  assert.equal(t.zaehler().tracksGestoppt, 1);
  assert.equal(t.zaehler().geleert, 2);
});
void test("Späte 401 einer alten Startanfrage meldet neues Gespräch nicht ab", async () => {
  const t = aufbau();
  const pending = offen<StartAntwort>();
  t.ports.starten = () => pending.promise;
  const alt = t.g.starten();
  await spuelen();
  t.g.beenden();
  t.ports.starten = () => Promise.resolve({ session_ref: "neu", sdp: "sdp", max_dauer_s: 600 });
  await t.g.starten();
  pending.ablehnen(new ApiFehler("Alt", 401));
  await alt;
  assert.equal(t.zaehler().abgemeldet, 0);
  assert.equal(t.zustaende.at(-1)?.phase, "gespraech");
  t.g.abmelden();
});

void test("Späte Startantwort mit fehlschlagendem /end meldet neues Gespräch nicht ab", async () => {
  const t = aufbau();
  const pending = offen<StartAntwort>();
  t.ports.starten = () => pending.promise;
  const alt = t.g.starten();
  await spuelen();
  t.g.beenden();
  t.ports.starten = () => Promise.resolve({ session_ref: "neu", sdp: "sdp", max_dauer_s: 600 });
  t.ports.beenden = () => Promise.reject(new ApiFehler("Alte Endanfrage", 401));
  await t.g.starten();
  pending.loesen({ session_ref: "alt", sdp: "sdp", max_dauer_s: 600 });
  await alt;
  await spuelen();
  assert.equal(t.zaehler().abgemeldet, 0);
  assert.equal(t.zustaende.at(-1)?.phase, "gespraech");
  t.g.abmelden();
});
void test("401 beim aktuellen Beenden löscht das Transkript und fordert Anmeldung", async () => {
  const t = aufbau();
  await t.g.starten();
  t.ports.beenden = () => Promise.reject(new ApiFehler("Bitte erneut anmelden.", 401));
  t.g.beenden();
  t.notizen.setzen("B", "Notiz während der Endanfrage");
  await spuelen();
  assert.equal(t.notizen.lesen("B"), "");
  assert.equal(t.zaehler().abgemeldet, 1);
  assert.equal(t.zaehler().geleert, 2);
});

void test("Neustart, Abmelden und Verlassen verwerfen sämtliche Notizen", async () => {
  const t = aufbau();
  await t.g.starten();
  t.g.beenden();
  t.notizen.setzen("X", "Notiz zum beendeten Gespräch");
  await t.g.starten();
  assert.equal(t.notizen.lesen("X"), "");
  t.notizen.setzen("Y", "Notiz vor Abmeldung");
  t.g.abmelden();
  assert.equal(t.notizen.lesen("Y"), "");
  await t.g.starten();
  t.notizen.setzen("Z", "Notiz vor Seitenwechsel");
  t.g.verlassen();
  assert.equal(t.notizen.lesen("Z"), "");
});

void test("Sitzungsrequests senden ausschließlich SDP oder Sitzungsreferenz, niemals Notizen", async (ctx) => {
  const anfragen: { pfad: unknown; body: unknown }[] = [];
  ctx.mock.method(globalThis, "fetch", (pfad: unknown, optionen: RequestInit) => {
    assert.equal(typeof optionen.body, "string");
    anfragen.push({ pfad, body: JSON.parse(optionen.body as string) as unknown });
    return Promise.resolve(
      pfad === "/api/session"
        ? new Response(
            JSON.stringify({ session_ref: "synthetisch", sdp: "antwort", max_dauer_s: 600 }),
          )
        : new Response(null, { status: 204 }),
    );
  });
  const t = aufbau();
  t.ports.starten = sitzungStarten;
  t.ports.beenden = sitzungBeenden;
  await t.g.starten();
  t.notizen.setzen("B", "DARF_NICHT_GESENDET_WERDEN");
  t.g.beenden();
  await spuelen();
  assert.equal(t.notizen.lesen("B"), "DARF_NICHT_GESENDET_WERDEN");
  await t.g.starten();
  t.g.beenden();
  await spuelen();
  assert.deepEqual(anfragen, [
    { pfad: "/api/session", body: { sdp: "angebot" } },
    { pfad: "/api/end", body: { session_ref: "synthetisch" } },
    { pfad: "/api/session", body: { sdp: "angebot" } },
    { pfad: "/api/end", body: { session_ref: "synthetisch" } },
  ]);
  assert.doesNotMatch(JSON.stringify(anfragen), /notizen|DARF_NICHT/u);
});

void test("Abschlusstext verwendet die öffentliche Persona und unterscheidet Endgründe", () => {
  assert.equal(
    abschlusstext("auflegen", "Alex Beispiel"),
    "Alex Beispiel hat aufgelegt. Das Gespräch ist beendet.",
  );
  assert.match(abschlusstext("nutzer"), /Sie haben/u);
  assert.match(abschlusstext("zeitlimit"), /abgelaufen/u);
  assert.match(abschlusstext("inaktiv"), /Inaktivität/u);
  assert.match(abschlusstext("verbindung_verloren"), /unterbrochen/u);
});
void test("Ausfall der optionalen Pegelanzeige blockiert den Gesprächsstart nicht", async () => {
  const t = aufbau();
  t.ports.analyse = () => {
    throw new Error("AudioContext fehlt");
  };
  await t.g.starten();
  assert.equal(t.zustaende.at(-1)?.phase, "gespraech");
  t.g.beenden();
  assert.equal(t.zaehler().tracksGestoppt, 1);
  assert.equal(t.zaehler().peerGestoppt, 1);
});
void test("Hängender Verbindungsaufbau endet nach 15 s; Uhr beginnt mit der Startantwort", async () => {
  const t = aufbau();
  t.ports.peer = () => ({
    angebot: () => Promise.resolve("sdp"),
    antwort: () => offen<undefined>().promise,
    stop() {},
  });
  const start = t.g.starten();
  await spuelen();
  assert.equal(t.zustaende.at(-1)?.start, 0);
  assert.equal(t.zustaende.at(-1)?.maxDauer, 600);
  await t.uhr.weiter(15000);
  assert.equal(t.zustaende.at(-1)?.phase, "beendet");
  assert.equal(t.zaehler().tracksGestoppt, 1);
  // Die absichtlich unaufgelöste Browser-Promise hält weder Timer noch Ressourcen.
  assert.ok(start instanceof Promise);
});
void test("Disconnect ohne Erholung beendet nach der Schonfrist", async () => {
  const t = aufbau();
  await t.g.starten();
  t.verbindung("disconnected");
  await t.uhr.weiter(5000);
  assert.equal(t.zustaende.at(-1)?.phase, "beendet");
  assert.equal(t.zaehler().tracksGestoppt, 1);
});
void test("Mikrofonfehler zeigt deutsche Hilfe und räumt Analyse auf", async () => {
  const t = aufbau();
  const fehler = new Error("verweigert");
  fehler.name = "NotAllowedError";
  t.ports.mikrofon = () => Promise.reject(fehler);
  await t.g.starten();
  assert.match(t.zustaende.at(-1)?.meldung ?? "", /Mikrofonzugriff/u);
  assert.equal(t.zaehler().analyseGestoppt, 1);
  assert.equal(t.zaehler().peerGestoppt, 0);
});

void test("Auch ein abgewiesener Beacon verhindert das lokale Aufräumen nicht", async () => {
  const t = aufbau();
  await t.g.starten();
  t.ports.beacon = () => {
    throw new Error("Beacon abgewiesen");
  };
  t.g.verlassen();
  assert.equal(t.zaehler().tracksGestoppt, 1);
  assert.equal(t.zaehler().peerGestoppt, 1);
  assert.equal(t.zaehler().herzStop, 1);
  assert.equal(t.zaehler().geleert, 2);
});
