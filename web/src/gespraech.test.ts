import { test } from "node:test";
import assert from "node:assert/strict";
import { abschlusstext, abschlussText, Gespraech } from "./gespraech.ts";
import type { AnrufAudio, Mikrofon, Ports, Zustand } from "./gespraech.ts";
import { ApiFehler } from "./api.ts";
import type { Messung, StartAntwort } from "./api.ts";
import type { HerzEnde } from "./herzschlag.ts";
import { ENDGRUENDE, serverGrund } from "./herzschlag.ts";
import { offen, spuelen, TestUhr } from "./testhilfe.ts";

function aufbau() {
  const uhr = new TestUhr();
  const zustaende: Zustand[] = [];
  const ansagen: string[] = [];
  const enden: { ref: string; messung?: Messung }[] = [];
  const messungen: Messung[] = [];
  const beacons: { ref: string; messung?: Messung }[] = [];
  const zahlen = {
    tracks: 0,
    peers: 0,
    audio: 0,
    herz: 0,
    leer: 0,
    auth: 0,
    starts: 0,
    bereit: 0,
    waehlen: 0,
    ruhe: 0,
    transkripte: 0,
  };
  const track = {
    enabled: true,
    stop() {
      zahlen.tracks++;
    },
  };
  const stream: Mikrofon = { getTracks: () => [track] };
  let audioErkannt = () => {};
  let audioWechsel = () => {};
  let callbacks: Parameters<Ports<Mikrofon>["peer"]>[2];
  let herzEnde: (e: HerzEnde) => void = () => {};
  let laeuft = true;
  let detektor = true;
  const audio: AnrufAudio = {
    mikrofon() {},
    remote() {},
    stop() {
      zahlen.audio++;
    },
    laeuft: () => laeuft,
    detektor: () => detektor,
    freigeben: () => {
      laeuft = true;
      return Promise.resolve(true);
    },
    waehlen() {
      zahlen.waehlen++;
    },
    ruhe() {
      zahlen.ruhe++;
    },
  };
  const ports: Ports<Mikrofon> = {
    uhr,
    analyse(erkannt, wechsel) {
      audioErkannt = erkannt;
      audioWechsel = wechsel;
      return audio;
    },
    mikrofon: () => Promise.resolve(stream),
    peer(_s, _a, cb) {
      callbacks = cb;
      return {
        angebot: () => Promise.resolve("angebot"),
        antwort: () => Promise.resolve(),
        freigeben: () => Promise.resolve(true),
        stop() {
          zahlen.peers++;
        },
      };
    },
    starten(_sdp, framework) {
      assert.equal(framework, "bant");
      zahlen.starts++;
      return Promise.resolve({ session_ref: "eins", sdp: "antwort", max_dauer_s: 600 });
    },
    bereit() {
      zahlen.bereit++;
      return Promise.resolve();
    },
    messung(_ref, m) {
      messungen.push(m);
      return Promise.resolve();
    },
    beenden(ref, messung) {
      enden.push({ ref, ...(messung ? { messung } : {}) });
      return Promise.resolve();
    },
    herz(_ref, cb) {
      herzEnde = cb;
      return () => {
        zahlen.herz++;
      };
    },
    beacon(ref, messung) {
      beacons.push({ ref, ...(messung ? { messung } : {}) });
    },
    zustand(w) {
      zustaende.push(w);
    },
    ansage(text) {
      ansagen.push(text);
    },
    leeren() {
      zahlen.leer++;
    },
    abgemeldet() {
      zahlen.auth++;
    },
    transkript() {
      zahlen.transkripte++;
    },
  };
  const g = new Gespraech(ports);
  return {
    g,
    uhr,
    ports,
    audio,
    zahlen,
    track,
    stream,
    zustaende,
    ansagen,
    enden,
    messungen,
    beacons,
    zustand: () => {
      const w = zustaende.at(-1);
      assert.ok(w);
      return w;
    },
    erkannt: () => {
      audioErkannt();
    },
    context: (running: boolean) => {
      laeuft = running;
      audioWechsel();
    },
    detektor: (aktiv: boolean) => {
      detektor = aktiv;
    },
    verbinden: () => {
      callbacks.verbindung("connected");
    },
    wiedergabe: (frei = true) => {
      callbacks.wiedergabe(frei);
    },
    verbindung: (s: string) => {
      callbacks.verbindung(s);
    },
    delta: (rolle: "sie" | "brandt" = "brandt") => {
      callbacks.transkript(rolle, "Synthetischer Text");
    },
    ende: (e: HerzEnde) => {
      herzEnde(e);
    },
    async c() {
      await g.starten("bant");
      g.ueberspringen();
      await spuelen();
    },
    async d() {
      await this.c();
      this.verbinden();
      this.wiedergabe();
      this.erkannt();
    },
  };
}

void test("Vollständiger Ablauf, Dauer ab Persona-Audio, Scoreboard 10 s; Pausen und Überspringen", async () => {
  const t = aufbau();
  await t.g.starten("bant");
  assert.equal(t.zustand().phase, "briefing");
  assert.equal(t.zahlen.starts, 0);
  await t.uhr.weiter(10000);
  t.g.pause();
  await t.uhr.weiter(60000);
  assert.equal(t.zustand().countdown, 10);
  t.g.pause();
  await t.uhr.weiter(10000);
  assert.equal(t.zustand().phase, "anwaehlen");
  assert.equal(t.track.enabled, false);
  t.verbinden();
  t.wiedergabe();
  await t.uhr.weiter(1400);
  t.erkannt();
  assert.equal(t.zustand().phase, "gespraech");
  assert.equal(t.track.enabled, true);
  assert.equal(t.zahlen.ruhe, 1);
  assert.deepEqual(t.messungen, [
    { status: "ok", c_bis_audio_ms: 1400, bereit_bis_audio_ms: 1400, c_bis_transkript_ms: null },
  ]);
  await t.uhr.weiter(4200);
  t.g.beenden();
  assert.equal(t.zustand().phase, "ausfuellen");
  assert.equal(t.zustand().abschluss?.dauer, 4200);
  assert.deepEqual(t.zustand().abschluss?.endgrund, { art: "lokal", grund: "nutzer" });
  assert.match(abschlussText({ art: "lokal", grund: "nutzer" }), /nicht bestätigt/u);
  t.g.fertig();
  await t.uhr.weiter(5000);
  t.g.pause();
  await t.uhr.weiter(20000);
  assert.equal(t.zustand().phase, "scoreboard");
  t.g.pause();
  await t.uhr.weiter(4999);
  assert.equal(t.zustand().phase, "scoreboard");
  await t.uhr.weiter(1);
  assert.equal(t.zustand().phase, "bereit");
  assert.equal(t.zustand().abschluss, null);
  assert.equal(t.zahlen.tracks, 1);
  assert.equal(t.zahlen.peers, 1);
  assert.equal(t.zahlen.audio, 1);
  assert.deepEqual(t.ansagen, [
    "Briefing, Anruf startet in 20 Sekunden.",
    "Briefing, Anruf startet in 5 Sekunden.",
    "Ergebnis, schließt in 10 Sekunden.",
    "Ergebnis, schließt in 5 Sekunden.",
  ]);
});

void test("Mikrofonablehnung: keine Sitzung; AudioContext synchron vor der Anfrage", async () => {
  const t = aufbau();
  const reihenfolge: string[] = [];
  const analyse = t.ports.analyse.bind(t.ports);
  t.ports.analyse = (...args) => {
    reihenfolge.push("audio");
    return analyse(...args);
  };
  t.ports.mikrofon = () => {
    reihenfolge.push("mic");
    return Promise.reject(new DOMException("", "NotAllowedError"));
  };
  const p = t.g.starten("bant");
  assert.deepEqual(reihenfolge, ["audio", "mic"]);
  await p;
  assert.equal(t.zustand().phase, "bereit");
  assert.match(t.zustand().meldung, /Mikrofonzugriff/u);
  assert.equal(t.zahlen.starts, 0);
  assert.equal(t.zahlen.audio, 1);
});
void test("Später Mikrofonstream nach Abbruch wird gestoppt; alte Generation startet nie", async () => {
  const t = aufbau();
  const mic = offen<Mikrofon>();
  t.ports.mikrofon = () => mic.promise;
  const p = t.g.starten("bant");
  t.g.beenden();
  mic.loesen(t.stream);
  await p;
  await t.uhr.weiter(500000);
  assert.equal(t.zustand().phase, "bereit");
  assert.equal(t.zahlen.tracks, 1);
  assert.equal(t.zahlen.starts, 0);
});
void test("Briefing-Abbruch und 5-min-Pausenfrist geben das Mikrofon ohne Sitzung frei", async () => {
  for (const pause of [false, true]) {
    const t = aufbau();
    await t.g.starten("bant");
    if (pause) {
      t.g.pause();
      await t.uhr.weiter(299999);
      assert.equal(t.zahlen.tracks, 0);
      await t.uhr.weiter(1);
    } else t.g.beenden();
    await t.uhr.weiter(60000);
    assert.equal(t.zustand().phase, "bereit");
    assert.equal(t.zahlen.starts, 0);
    assert.equal(t.zahlen.tracks, 1);
  }
});
void test("Bereit erst nach connected UND play UND laufendem Context, genau einmal", async () => {
  const t = aufbau();
  t.context(false);
  await t.c();
  t.verbinden();
  assert.equal(t.zahlen.bereit, 0);
  t.wiedergabe();
  assert.equal(t.zahlen.bereit, 0);
  assert.equal(t.zustand().tonBlockiert, true);
  t.context(true);
  assert.equal(t.zahlen.bereit, 1);
  t.verbinden();
  t.wiedergabe();
  await t.g.tonAktivieren();
  assert.equal(t.zahlen.bereit, 1);
  assert.equal(t.zustand().phase, "anwaehlen");
  t.g.beenden();
});
void test("Hängende Tonfreigabe wird nach 30 s begrenzt; späte Freigabe bleibt wirkungslos", async () => {
  const t = aufbau();
  const freigabe = offen<boolean>();
  t.audio.freigeben = () => freigabe.promise;
  await t.c();
  t.verbinden();
  t.wiedergabe(false);
  const p = t.g.tonAktivieren();
  await t.uhr.weiter(29999);
  assert.equal(t.zustand().phase, "anwaehlen");
  await t.uhr.weiter(1);
  assert.equal(t.zustand().phase, "bereit");
  assert.equal(t.zahlen.bereit, 0);
  assert.equal(t.zahlen.tracks, 1);
  freigabe.loesen(true);
  await p;
  assert.equal(t.zahlen.bereit, 0);
  assert.equal(t.enden[0]?.messung?.status, "abbruch");
});
void test("15-s-Audiofrist beginnt erst bei bereit; Stille führt nach D mit offenem Mikrofon", async () => {
  const t = aufbau();
  await t.c();
  t.verbinden();
  await t.uhr.weiter(14000);
  assert.equal(t.zustand().phase, "anwaehlen");
  t.wiedergabe();
  await t.uhr.weiter(14999);
  assert.equal(t.track.enabled, false);
  await t.uhr.weiter(1);
  assert.equal(t.zustand().phase, "gespraech");
  assert.equal(t.track.enabled, true);
  assert.match(t.zustand().meldung, /still/u);
  assert.deepEqual(t.messungen, [
    { status: "frist", c_bis_audio_ms: null, bereit_bis_audio_ms: null, c_bis_transkript_ms: null },
  ]);
  t.g.beenden();
  assert.equal(t.zustand().abschluss?.signal, "frist");
});
void test("Transkript als Ersatz nur bei Detektorausfall: Audiowerte bleiben null", async () => {
  const t = aufbau();
  await t.c();
  t.verbinden();
  t.wiedergabe();
  t.delta("sie");
  assert.equal(t.zustand().phase, "anwaehlen");
  await t.uhr.weiter(30);
  t.delta();
  assert.equal(t.zustand().phase, "anwaehlen");
  t.detektor(false);
  await t.uhr.weiter(50);
  t.delta();
  assert.equal(t.zustand().phase, "gespraech");
  assert.deepEqual(t.messungen, [
    { status: "ok", c_bis_audio_ms: null, bereit_bis_audio_ms: null, c_bis_transkript_ms: 30 },
  ]);
  t.erkannt();
  assert.equal(t.messungen.length, 1);
  t.g.beenden();
  assert.equal(t.zustand().abschluss?.signal, "transkript");
});
void test("C-Abbruch mit später Startantwort schließt gezielt; kein E1 und keine alte Änderung", async () => {
  const t = aufbau();
  const start = offen<StartAntwort>();
  t.ports.starten = () => start.promise;
  await t.c();
  t.g.beenden();
  await t.g.starten("bant");
  start.loesen({ session_ref: "alt", sdp: "antwort", max_dauer_s: 600 });
  await spuelen();
  assert.equal(t.zustand().phase, "briefing");
  assert.equal(t.enden[0]?.ref, "alt");
  assert.equal(t.enden[0].messung?.status, "abbruch");
  t.g.beenden();
});
void test("Abbruch in C übermittelt genau das Messschema; Messfehler blockieren das Ende nie", async () => {
  const t = aufbau();
  await t.c();
  t.g.beenden();
  assert.deepEqual(t.enden, [
    {
      ref: "eins",
      messung: {
        status: "abbruch",
        c_bis_audio_ms: null,
        bereit_bis_audio_ms: null,
        c_bis_transkript_ms: null,
      },
    },
  ]);
  const d = aufbau();
  d.ports.messung = () => offen<unknown>().promise;
  await d.d();
  d.g.beenden();
  assert.equal(d.zustand().phase, "ausfuellen");
});
for (const inD of [false, true]) {
  for (const art of ["failed", "disconnected", "herzfrist", "server", "404"] as const)
    void test(`${art} ${inD ? "nach" : "vor"} Gesprächsbeginn: ${inD ? "E1" : "A"}`, async () => {
      const t = aufbau();
      if (inD) await t.d();
      else await t.c();
      if (art === "herzfrist") t.ende({ art: "frist" });
      else if (art === "server") t.ende({ art: "ende", grund: "auflegen" });
      else if (art === "404") t.ende({ art: "ende", grund: null });
      else {
        t.verbindung(art);
        if (art === "disconnected") await t.uhr.weiter(5000);
      }
      assert.equal(t.zustand().phase, inD ? "ausfuellen" : "bereit");
      assert.equal(t.zahlen.audio, 1);
      assert.equal(t.zahlen.tracks, 1);
      if (art === "server" || art === "404") {
        assert.equal(t.enden.length, 0);
        if (!inD) assert.equal(t.messungen.length, 0);
      }
    });
}
void test("Disconnect erholt sich innerhalb 5 s; alte Timer beenden keine Verbindung", async () => {
  const t = aufbau();
  await t.d();
  t.verbindung("disconnected");
  await t.uhr.weiter(4999);
  t.verbinden();
  await t.uhr.weiter(10000);
  assert.equal(t.zustand().phase, "gespraech");
  t.g.beenden();
});
void test("15-s-Verbindungsfrist läuft unabhängig von hängender RemoteDescription", async () => {
  const t = aufbau();
  const peer = t.ports.peer.bind(t.ports);
  t.ports.peer = (...args) => ({ ...peer(...args), antwort: () => offen<undefined>().promise });
  await t.c();
  await t.uhr.weiter(15000);
  assert.equal(t.zustand().phase, "bereit");
  assert.equal(t.zahlen.tracks, 1);
});
for (const phase of ["anwaehlen", "gespraech", "ausfuellen", "scoreboard"] as const)
  void test(`401 in ${phase} löscht Daten und Abschluss, alte Arbeit ist wirkungslos`, async () => {
    const t = aufbau();
    const ende = offen<unknown>();
    t.ports.beenden = () => ende.promise;
    if (phase === "anwaehlen") await t.c();
    else await t.d();
    if (phase === "ausfuellen" || phase === "scoreboard") {
      t.g.beenden();
      if (phase === "scoreboard") t.g.fertig();
    }
    const leer = t.zahlen.leer;
    if (phase === "anwaehlen" || phase === "gespraech") t.ende({ art: "anmeldung" });
    else {
      ende.ablehnen(new ApiFehler("Anmeldung abgelaufen", 401));
      await spuelen();
    }
    assert.equal(t.zahlen.auth, 1);
    assert.ok(t.zahlen.leer > leer);
    t.delta();
    t.erkannt();
    await t.uhr.weiter(30000);
    assert.equal(t.zahlen.transkripte, 0);
  });
void test("401 aus bereit oder Messung führt zur Anmeldung; andere Messfehler werden ignoriert", async () => {
  for (const pfad of ["bereit", "messung"] as const) {
    const t = aufbau();
    t.ports[pfad] = () => Promise.reject(new ApiFehler("Erneut anmelden", 401));
    await t.d();
    await spuelen();
    assert.equal(t.zahlen.auth, 1);
  }
  const t = aufbau();
  t.ports.messung = () => Promise.reject(new ApiFehler("Netzfehler", 0));
  await t.d();
  await spuelen();
  assert.equal(t.zustand().phase, "gespraech");
  t.g.beenden();
});
void test("Alle Server-Endgründe und unbekannte Gründe bleiben getrennt von lokalen Fehlern", async () => {
  for (const grund of [...ENDGRUENDE, "unbekannt"] as const) {
    const t = aufbau();
    await t.d();
    t.ende({ art: "ende", grund });
    assert.deepEqual(t.zustand().abschluss?.endgrund, { art: "server", grund });
    assert.ok(abschlusstext(grund));
  }
  assert.equal(serverGrund("neu_vom_server"), "unbekannt");
});
void test("Pagehide in B/C/D und Scoreboard stoppt alles; Beacon in C enthält Abbruchmessung", async () => {
  for (const phase of ["B", "C", "D", "E2"]) {
    const t = aufbau();
    if (phase === "B") await t.g.starten("bant");
    else if (phase === "C") await t.c();
    else await t.d();
    if (phase === "E2") {
      t.g.beenden();
      t.g.fertig();
    }
    t.g.verlassen();
    const anzahl = t.zustaende.length;
    await t.uhr.weiter(600000);
    assert.equal(t.zustaende.length, anzahl);
    assert.equal(t.zahlen.tracks, 1);
    if (phase === "C") assert.equal(t.beacons[0]?.messung?.status, "abbruch");
  }
});
void test("Scoreboard überspringen löscht Abschluss sofort", async () => {
  const t = aufbau();
  await t.d();
  t.g.beenden();
  t.g.fertig();
  t.g.ueberspringen();
  assert.equal(t.zustand().phase, "bereit");
  assert.equal(t.zustand().abschluss, null);
});

void test("Erneute Tonblockade nach bereit darf Mikrofon nicht über die 15-s-Frist freigeben", async () => {
  const t = aufbau();
  await t.c();
  t.verbinden();
  t.wiedergabe();
  t.context(false);
  await t.uhr.weiter(15000);
  assert.equal(t.zustand().phase, "anwaehlen");
  assert.equal(t.track.enabled, false);
  t.context(true);
  assert.equal(t.zustand().phase, "gespraech");
  assert.equal(t.zahlen.bereit, 1);
  assert.equal(t.track.enabled, true);
  t.g.beenden();
});
void test("Startfehler 401 löscht, 429 kehrt mit Servermeldung zu A zurück", async () => {
  for (const status of [401, 429]) {
    const t = aufbau();
    t.ports.starten = () => Promise.reject(new ApiFehler("Synthetische Meldung", status));
    await t.c();
    assert.equal(t.zahlen.tracks, 1);
    if (status === 401) assert.equal(t.zahlen.auth, 1);
    else {
      assert.equal(t.zustand().phase, "bereit");
      assert.equal(t.zustand().meldung, "Synthetische Meldung");
    }
  }
});
void test("Alte 401 von Start oder gezieltem Ende meldet die neue Generation nicht ab", async () => {
  for (const erfolg of [false, true]) {
    const t = aufbau();
    const start = offen<StartAntwort>();
    t.ports.starten = () => start.promise;
    await t.c();
    t.g.beenden();
    await t.g.starten("bant");
    t.ports.beenden = () => Promise.reject(new ApiFehler("Alt", 401));
    if (erfolg) start.loesen({ session_ref: "alt", sdp: "alt", max_dauer_s: 600 });
    else start.ablehnen(new ApiFehler("Alt", 401));
    await spuelen();
    assert.equal(t.zahlen.auth, 0);
    assert.equal(t.zustand().phase, "briefing");
    t.g.beenden();
  }
});
