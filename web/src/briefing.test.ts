import { test } from "node:test";
import assert from "node:assert/strict";
import { briefingModell, Notizen } from "./briefing.ts";
import type { Briefing } from "./api.ts";

void test("Briefing-JSON bildet öffentliche Angaben und beliebige Kriterien ohne Treffer ab", () => {
  // Bewusst andere synthetische Daten als die aktuelle Server-Persona.
  const daten: Briefing = JSON.parse(`{
    "persona": {"name":"Alex Beispiel", "rolle":"Einkauf", "unternehmen":"Testbetrieb",
      "standorte":"Bremen", "hinweis":"Ein erstes Kennenlernen."},
    "produkt":{"name":"Testprodukt","nutzen":"Einsatzplanung","preis":"Preis auf Anfrage"},
    "ziel":"Bedarf verstehen", "punkte":["Fragen zählen", "Termin zählt"],
    "framework":{"id":"test","name":"Test-Framework","quelle":"Ihr Team",
      "kriterien":[{"key":"X","label":"Anforderung","leitfrage":"Was brauchen Sie?"},
        {"key":"Y","label":"Verfahren","leitfrage":"Wie entscheiden Sie?"}]},
    "frameworks":[{"id":"test","name":"Test-Framework","verfuegbar":true}],
    "aufgaben":["Bedarf verstehen"], "max_dauer_s":450
  }`) as Briefing;
  const vorher = JSON.stringify(daten);
  const modell = briefingModell(daten);
  assert.deepEqual(modell, {
    titel: "Rufen Sie Alex Beispiel an.",
    ziel: "Bedarf verstehen",
    name: "Alex Beispiel",
    beschreibung: "Einkauf · Testbetrieb · Bremen",
    produkt: "Testprodukt – Einsatzplanung",
    fakten: [
      { label: "Gesprächspartner", wert: "Alex Beispiel, Einkauf" },
      { label: "Unternehmen", wert: "Testbetrieb" },
      { label: "Standorte", wert: "Bremen" },
      { label: "Ihr Produkt", wert: "Testprodukt – Einsatzplanung" },
      { label: "Preis", wert: "Preis auf Anfrage" },
    ],
    dauer: "7,5 Minuten",
    hinweis: "Ein erstes Kennenlernen.",
    framework: "Test-Framework",
    quelle: "Ihr Team",
    kriterien: [
      {
        key: "X",
        label: "Anforderung",
        leitfrage: "Was brauchen Sie?",
        status: "offen",
        gespraechStatus: "folgt",
      },
      {
        key: "Y",
        label: "Verfahren",
        leitfrage: "Wie entscheiden Sie?",
        status: "offen",
        gespraechStatus: "folgt",
      },
    ],
    punkte: ["Fragen zählen", "Termin zählt"],
  });
  assert.equal(JSON.stringify(daten), vorher);
});

void test("Notizen werden nur lokal je Schlüssel gehalten und vollständig verworfen", () => {
  const notizen = new Notizen();
  notizen.setzen("X", "Synthetische Notiz");
  notizen.setzen("Y", "Andere Notiz");
  assert.equal(notizen.lesen("X"), "Synthetische Notiz");
  assert.equal(notizen.lesen("unbekannt"), "");
  notizen.leeren();
  assert.equal(notizen.lesen("X"), "");
  assert.equal(notizen.lesen("Y"), "");
});

void test("Scoreboard zählt ausschließlich ausgefüllte Kriterien, keine Leerzeichen oder fremde Schlüssel", () => {
  const notizen = new Notizen();
  notizen.setzen("B", "Synthetischer Betrag");
  notizen.setzen("A", "  ");
  notizen.setzen("fremd", "Zählt nicht");
  assert.equal(notizen.ausgefuellt(["B", "A", "N", "T"]), 1);
  notizen.leeren();
  assert.equal(notizen.ausgefuellt(["B", "A", "N", "T"]), 0);
});
