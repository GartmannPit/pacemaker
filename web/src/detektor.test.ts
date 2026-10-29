import { test } from "node:test";
import assert from "node:assert/strict";
import { AudioDetektor } from "./detektor.ts";

void test("Stille und kurze Impulse lösen nicht aus; 60 ms oberhalb RMS 0,01 genau einmal", () => {
  const d = new AudioDetektor();
  for (let t = 0; t < 1000; t += 20) assert.equal(d.pruefen(0.001, t), false);
  assert.equal(d.pruefen(0.02, 1000), false);
  assert.equal(d.pruefen(0, 1020), false);
  for (const t of [1040, 1060, 1080]) assert.equal(d.pruefen(0.02, t), false);
  assert.equal(d.pruefen(0.02, 1100), true);
  assert.equal(d.pruefen(0.1, 1120), false);
});
void test("Tab-Drosselung und ungültige Samples zählen nicht als durchgehendes Audio", () => {
  const d = new AudioDetektor();
  assert.equal(d.pruefen(0.1, 0), false);
  assert.equal(d.pruefen(0.1, 5000), false);
  assert.equal(d.pruefen(NaN, 5020), false);
  for (const t of [5040, 5060, 5080]) assert.equal(d.pruefen(0.1, t), false);
  assert.equal(d.pruefen(0.1, 5100), true);
});
