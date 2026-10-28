import { test } from "node:test";
import assert from "node:assert/strict";
import { herzschlagStarten } from "./herzschlag.ts";
import type { HerzEnde } from "./herzschlag.ts";
import { offen, spuelen, TestUhr } from "./testhilfe.ts";

function antwort(zustand = "laufend", grund: string | null = null) {
  return Response.json({ zustand, grund });
}
void test("Takt 5 s, gültige Bestätigung verschiebt die Frist, Stop räumt Timer auf", async () => {
  const uhr = new TestUhr();
  const ereignisse: HerzEnde[] = [];
  const zeiten: number[] = [];
  const stop = herzschlagStarten(
    "eins",
    (e) => {
      ereignisse.push(e);
    },
    {
      uhr,
      fetch: (_url, init) => {
        zeiten.push(uhr.jetzt());
        assert.equal(init?.body, JSON.stringify({ session_ref: "eins" }));
        return Promise.resolve(antwort());
      },
    },
  );
  await uhr.weiter(4999);
  assert.equal(zeiten.length, 0);
  await uhr.weiter(1);
  assert.deepEqual(zeiten, [5000]);
  await uhr.weiter(15000);
  assert.deepEqual(zeiten, [5000, 10000, 15000, 20000]);
  assert.deepEqual(ereignisse, []);
  stop();
  await uhr.weiter(30000);
  assert.equal(zeiten.length, 4);
  assert.deepEqual(ereignisse, []);
});
void test("Hängende Anfrage: Abort nach 4 s, höchstens eine Anfrage, lokale Frist exakt 15 s", async () => {
  const uhr = new TestUhr();
  const ereignisse: HerzEnde[] = [];
  const pending = offen<Response>();
  let signal: AbortSignal | null | undefined;
  let anzahl = 0;
  herzschlagStarten(
    "eins",
    (e) => {
      ereignisse.push(e);
    },
    {
      uhr,
      fetch: (_url, init) => {
        anzahl++;
        signal = init?.signal;
        return pending.promise;
      },
    },
  );
  await uhr.weiter(8999);
  assert.equal(signal?.aborted, false);
  await uhr.weiter(1);
  assert.equal(signal.aborted, true);
  await uhr.weiter(5999);
  assert.deepEqual(ereignisse, []);
  assert.equal(anzahl, 1);
  await uhr.weiter(1);
  assert.deepEqual(ereignisse, [{ art: "frist" }]);
  pending.loesen(antwort());
  await spuelen();
  assert.equal(ereignisse.length, 1);
});
for (const status of [401, 404])
  void test(`HTTP ${String(status)} beendet sofort`, async () => {
    const uhr = new TestUhr();
    const ereignisse: HerzEnde[] = [];
    herzschlagStarten(
      "eins",
      (e) => {
        ereignisse.push(e);
      },
      { uhr, fetch: () => Promise.resolve(new Response(null, { status })) },
    );
    await uhr.weiter(5000);
    assert.deepEqual(ereignisse, [
      status === 401 ? { art: "anmeldung" } : { art: "ende", grund: null },
    ]);
    await uhr.weiter(20000);
    assert.equal(ereignisse.length, 1);
  });
for (const zustand of ["endend", "beendet"])
  void test(`200 ${zustand} gibt Endgrund weiter`, async () => {
    const uhr = new TestUhr();
    const ereignisse: HerzEnde[] = [];
    herzschlagStarten(
      "eins",
      (e) => {
        ereignisse.push(e);
      },
      { uhr, fetch: () => Promise.resolve(antwort(zustand, "auflegen")) },
    );
    await uhr.weiter(5000);
    assert.deepEqual(ereignisse, [{ art: "ende", grund: "auflegen" }]);
  });
void test("5xx und Netzfehler bestätigen nichts; Frist läuft seit letzter gültiger Antwort", async () => {
  const uhr = new TestUhr();
  const ereignisse: HerzEnde[] = [];
  let anzahl = 0;
  herzschlagStarten(
    "eins",
    (e) => {
      ereignisse.push(e);
    },
    {
      uhr,
      fetch: () => {
        anzahl++;
        if (anzahl === 1) return Promise.resolve(antwort());
        if (anzahl === 2) return Promise.resolve(new Response(null, { status: 503 }));
        return Promise.reject(new Error("Netz aus"));
      },
    },
  );
  await uhr.weiter(19999);
  assert.deepEqual(ereignisse, []);
  await uhr.weiter(1);
  assert.deepEqual(ereignisse, [{ art: "frist" }]);
  assert.equal(anzahl, 3);
});
void test("Ungültige 200-Antwort verlängert die Frist nicht", async () => {
  const uhr = new TestUhr();
  const ereignisse: HerzEnde[] = [];
  herzschlagStarten(
    "eins",
    (e) => {
      ereignisse.push(e);
    },
    { uhr, fetch: () => Promise.resolve(Response.json({ zustand: "unbekannt" })) },
  );
  await uhr.weiter(15000);
  assert.deepEqual(ereignisse, [{ art: "frist" }]);
});
void test("Verspätete alte Antwort nach Neustart bleibt wirkungslos", async () => {
  const uhr = new TestUhr();
  const ereignisse: HerzEnde[] = [];
  const pending = offen<Response>();
  const stop = herzschlagStarten(
    "alt",
    (e) => {
      ereignisse.push(e);
    },
    { uhr, fetch: () => pending.promise },
  );
  await uhr.weiter(5000);
  stop();
  const neuStop = herzschlagStarten(
    "neu",
    (e) => {
      ereignisse.push(e);
    },
    { uhr, fetch: () => Promise.resolve(antwort()) },
  );
  pending.loesen(new Response(null, { status: 401 }));
  await spuelen();
  await uhr.weiter(20000);
  assert.deepEqual(ereignisse, []);
  neuStop();
});
void test("Hängender JSON-Body wird nach 4 s abgebrochen und bestätigt nichts", async () => {
  const uhr = new TestUhr();
  const ereignisse: HerzEnde[] = [];
  const body = offen<unknown>();
  herzschlagStarten(
    "eins",
    (e) => {
      ereignisse.push(e);
    },
    {
      uhr,
      fetch: () => {
        const r = antwort();
        r.json = () => body.promise;
        return Promise.resolve(r);
      },
    },
  );
  await uhr.weiter(15000);
  body.loesen({ zustand: "laufend", grund: null });
  await spuelen();
  assert.deepEqual(ereignisse, [{ art: "frist" }]);
});
