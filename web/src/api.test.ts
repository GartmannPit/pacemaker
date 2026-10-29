import { test } from "node:test";
import assert from "node:assert/strict";
import { sitzungStarten, sitzungBeenden } from "./api.ts";
import type { Messung } from "./api.ts";

void test("Requests enthalten Framework und optional Messung, keine Gesprächsinhalte", async (ctx) => {
  const anfragen: { pfad: unknown; body: unknown }[] = [];
  ctx.mock.method(globalThis, "fetch", (pfad: unknown, optionen: RequestInit) => {
    assert.equal(optionen.credentials, "same-origin");
    anfragen.push({ pfad, body: JSON.parse(optionen.body as string) as unknown });
    return Promise.resolve(
      Response.json(
        pfad === "/api/session" ? { session_ref: "eins", sdp: "antwort", max_dauer_s: 600 } : {},
      ),
    );
  });
  const messung: Messung = {
    status: "abbruch",
    c_bis_audio_ms: null,
    bereit_bis_audio_ms: null,
    c_bis_transkript_ms: 120,
  };
  await sitzungStarten("angebot", "bant");
  await sitzungBeenden("eins", messung);
  await sitzungBeenden("zwei");
  assert.deepEqual(anfragen, [
    { pfad: "/api/session", body: { sdp: "angebot", framework_id: "bant" } },
    { pfad: "/api/end", body: { session_ref: "eins", messung } },
    { pfad: "/api/end", body: { session_ref: "zwei" } },
  ]);
});
