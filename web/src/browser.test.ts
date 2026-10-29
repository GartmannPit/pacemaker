import { test } from "node:test";
import assert from "node:assert/strict";
import { browserVerbindung } from "./gespraech.ts";
import { offen, spuelen } from "./testhilfe.ts";

void test("Browseradapter: stummer Track, Wiedergabefreigabe, Ereignis-Allowlist und Aufräumen", async (ctx) => {
  const mic = { enabled: false, stop() {} };
  let remoteStop = 0;
  const remoteTrack = {
    stop() {
      remoteStop++;
    },
  };
  class Stream {
    private readonly tracks: unknown[];
    constructor(tracks: unknown[]) {
      this.tracks = tracks;
    }
    getTracks() {
      return this.tracks;
    }
  }
  function globalErsetzen(name: string, wert: unknown) {
    const vorher = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { value: wert, configurable: true, writable: true });
    ctx.after(() => {
      if (vorher) Object.defineProperty(globalThis, name, vorher);
      else Reflect.deleteProperty(globalThis, name);
    });
  }
  globalErsetzen("MediaStream", Stream);
  const kanal = {
    onmessage: null as ((e: MessageEvent<unknown>) => void) | null,
    close() {},
    send() {
      assert.fail("Keine Browser-Steuerereignisse senden");
    },
  };
  class Peer {
    static letzter: Peer;
    ontrack: ((e: RTCTrackEvent) => void) | null = null;
    onconnectionstatechange: (() => void) | null = null;
    oniceconnectionstatechange: (() => void) | null = null;
    connectionState = "connected";
    iceConnectionState = "connected";
    iceGatheringState = "complete";
    localDescription = { sdp: "angebot" };
    geschlossen = false;
    constructor() {
      Peer.letzter = this;
    }
    addTrack(track: typeof mic) {
      assert.equal(track.enabled, false);
    }
    createDataChannel() {
      return kanal;
    }
    createOffer() {
      return Promise.resolve({ sdp: "angebot" });
    }
    setLocalDescription() {
      return Promise.resolve();
    }
    setRemoteDescription() {
      return Promise.resolve();
    }
    close() {
      this.geschlossen = true;
    }
  }
  globalErsetzen("RTCPeerConnection", Peer);
  const play = offen<undefined>();
  let pausen = 0;
  const audio = {
    srcObject: null as unknown,
    play: () => play.promise,
    pause() {
      pausen++;
    },
  };
  let analysiert = 0;
  const frei: boolean[] = [];
  const transkripte: string[] = [];
  const verbindung = browserVerbindung(
    { getAudioTracks: () => [mic], getTracks: () => [mic] } as unknown as MediaStream,
    {
      mikrofon() {},
      remote() {
        analysiert++;
      },
      stop() {},
    },
    audio as unknown as HTMLAudioElement,
    {
      wiedergabe: (wert) => {
        frei.push(wert);
      },
      verbindung() {},
      transkript: (rolle, delta) => {
        transkripte.push(`${rolle}:${delta}`);
      },
    },
  );
  assert.equal(await verbindung.angebot(new AbortController().signal), "angebot");
  Peer.letzter.ontrack?.({ track: remoteTrack } as unknown as RTCTrackEvent);
  assert.deepEqual(frei, [false]); // Auch hängendes play() meldet sofort Freigabebedarf.
  assert.equal(analysiert, 1);
  const senden = (type: string) => {
    kanal.onmessage?.({ data: JSON.stringify({ type, delta: "Test" }) } as MessageEvent);
  };
  senden("session.output_transcript.delta");
  senden("session.input_transcript.delta");
  senden("session.commentary.append");
  senden("response.create");
  assert.deepEqual(transkripte, ["brandt:Test", "sie:Test"]);
  play.loesen(undefined);
  await spuelen();
  assert.deepEqual(frei, [false, true]);
  assert.equal(await verbindung.freigeben(), true);
  verbindung.stop();
  assert.equal(remoteStop, 1);
  assert.equal(pausen, 1);
  assert.equal(audio.srcObject, null);
  assert.equal(Peer.letzter.geschlossen, true);
  assert.equal(kanal.onmessage, null);
});
