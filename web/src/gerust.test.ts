import { test } from "node:test";
import assert from "node:assert/strict";

void test("Test-Runner läuft mit Type-Stripping", () => {
  const wert: number = 1;
  assert.equal(wert, 1);
});
