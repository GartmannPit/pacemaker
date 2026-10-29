import { test } from "node:test";
import assert from "node:assert/strict";
import { anrufAudioStarten } from "./anruf-audio.ts";
import { spuelen } from "./testhilfe.ts";

void test("Wählton hat eigenen Ausgang; Detektor arbeitet bei ausgeschalteter Anzeige und stoppt mit dem Context", async (ctx) => {
  let jetzt = 0;
  ctx.mock.method(performance, "now", () => jetzt);
  ctx.mock.timers.enable({ apis: ["setTimeout"] });
  const kanten: string[] = [];
  let rms = 0;
  let geschlossen = 0;
  let erkannt = 0;
  let visualStop = 0;
  const oszillatoren: { gestoppt: boolean }[] = [];
  class Knoten {
    readonly name: string;
    constructor(name: string) {
      this.name = name;
    }
    connect(ziel: Knoten) {
      kanten.push(`${this.name}→${ziel.name}`);
    }
    disconnect() {}
  }
  class Context {
    state = "running";
    currentTime = 0;
    onstatechange = null;
    destination = new Knoten("ausgang");
    resume() {
      return Promise.resolve();
    }
    close() {
      geschlossen++;
      return Promise.resolve();
    }
    createGain() {
      return Object.assign(new Knoten("gain"), {
        gain: { setValueAtTime() {}, linearRampToValueAtTime() {} },
      });
    }
    createOscillator() {
      const ton = Object.assign(new Knoten("ton"), {
        frequency: { value: 0 },
        onended: null,
        gestoppt: false,
        start() {},
        stop() {
          this.gestoppt = true;
        },
      });
      oszillatoren.push(ton);
      return ton;
    }
    createMediaStreamSource() {
      return new Knoten("persona");
    }
    createAnalyser() {
      return Object.assign(new Knoten("analyse"), {
        fftSize: 1024,
        getFloatTimeDomainData(daten: Float32Array) {
          daten.fill(rms);
        },
      });
    }
  }
  const vorher = Object.getOwnPropertyDescriptor(globalThis, "AudioContext");
  Object.defineProperty(globalThis, "AudioContext", { value: Context, configurable: true });
  ctx.after(() => {
    if (vorher) Object.defineProperty(globalThis, "AudioContext", vorher);
    else Reflect.deleteProperty(globalThis, "AudioContext");
  });
  const audio = anrufAudioStarten(
    () => {
      erkannt++;
    },
    () => {},
    () => ({
      mikrofon() {},
      remote() {},
      stop() {
        visualStop++;
      },
    }),
  );
  await spuelen();
  audio.waehlen();
  audio.remote({} as MediaStream);
  for (let i = 0; i < 5; i++) {
    jetzt += 20;
    ctx.mock.timers.tick(20);
  }
  assert.equal(erkannt, 0); // Der Wählton erreicht den Detektor nicht.
  assert.equal(audio.detektor(), true);
  rms = 0.03;
  for (let i = 0; i < 4; i++) {
    jetzt += 20;
    ctx.mock.timers.tick(20);
  }
  assert.equal(erkannt, 1);
  assert.ok(kanten.includes("persona→analyse"));
  assert.ok(kanten.includes("ton→gain"));
  assert.ok(kanten.includes("gain→ausgang"));
  assert.ok(!kanten.includes("analyse→ausgang"));
  assert.ok(!kanten.includes("ton→analyse"));
  audio.ruhe();
  assert.ok(oszillatoren.every((ton) => ton.gestoppt));
  audio.stop();
  assert.equal(geschlossen, 1);
  assert.equal(visualStop, 1);
  assert.equal(audio.detektor(), false);
  ctx.mock.timers.tick(10000);
  assert.equal(erkannt, 1);
});
