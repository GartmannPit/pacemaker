import "./style.css";
import { api, ApiFehler, fehlermeldung, sitzungStarten, sitzungBeenden } from "./api.ts";
import type { Briefing, Kontingent } from "./api.ts";
import { Ansicht, element } from "./ansicht.ts";
import { browserVerbindung, Gespraech, herzschlagStarten, systemUhr } from "./gespraech.ts";
import { anrufAudioStarten } from "./anruf-audio.ts";
import { PEGEL_AKTIV, pegelStarten } from "./pegel.ts";
import type { Pegel } from "./pegel.ts";

const ansicht = new Ansicht();
const audio = element<HTMLAudioElement>("audio");
let benutzer = "";
let revision = 0;
let ladeRevision = 0;
let pegel: Pegel | null = null;
let pegelEin = PEGEL_AKTIV && new URLSearchParams(location.search).get("pegel") !== "0";
function pegelKnopf() {
  element("pegel-schalter").setAttribute("aria-pressed", String(pegelEin));
  element("pegel-schalter").textContent = pegelEin
    ? "Pegelanzeige ausschalten"
    : "Pegelanzeige einschalten";
}
function anmeldung(meldung: string) {
  revision++;
  benutzer = "";
  gespraech.abmelden();
  pegel = null;
  element<HTMLInputElement>("passwort").value = "";
  element("anmeldefehler").hidden = true;
  element("name").removeAttribute("aria-describedby");
  ansicht.anmeldung(meldung);
}
const gespraech = new Gespraech<MediaStream>({
  uhr: systemUhr,
  analyse(erkannt, aenderung) {
    pegelEin = PEGEL_AKTIV && new URLSearchParams(location.search).get("pegel") !== "0";
    pegelKnopf();
    return anrufAudioStarten(erkannt, aenderung, (context) => {
      pegel = pegelStarten(
        element<HTMLCanvasElement>("ringe"),
        (e, b) => {
          ansicht.pegel(e, b);
        },
        (aktiv) => {
          element("pegel-status").textContent = aktiv
            ? "Pegelanzeige aktiv"
            : "Pegelanzeige nicht aktiv; das Gespräch ist davon unabhängig.";
        },
        context,
      );
      return pegel;
    });
  },
  mikrofon: () => navigator.mediaDevices.getUserMedia({ audio: true }),
  peer: (stream, analyse, callbacks) => browserVerbindung(stream, analyse, audio, callbacks),
  starten: sitzungStarten,
  beenden: sitzungBeenden,
  bereit: (session_ref) => api("/api/session/bereit", { session_ref }),
  messung: (session_ref, messung) => api("/api/session/messung", { session_ref, messung }),
  personaName: () => ansicht.gegenueber(),
  herz: (ref, ende) => herzschlagStarten(ref, ende),
  beacon: (ref, messung) => {
    navigator.sendBeacon(
      "/api/end",
      new Blob(
        [JSON.stringify({ session_ref: ref, grund: "tab", ...(messung ? { messung } : {}) })],
        { type: "application/json" },
      ),
    );
  },
  zustand(wert) {
    ansicht.aktualisieren(wert);
    if (["bereit", "ausfuellen"].includes(wert.phase)) pegel = null;
    if (wert.phase === "bereit" && benutzer) void statusLaden(false);
  },
  ansage: (text) => {
    ansicht.ansage(text);
  },
  transkript: (rolle, delta) => {
    ansicht.transkript(rolle, delta);
  },
  leeren: () => {
    ansicht.leeren();
  },
  abgemeldet: anmeldung,
});

async function statusLaden(briefingLaden = true) {
  const aktuell = revision;
  const ladung = ++ladeRevision;
  element<HTMLButtonElement>("start").disabled = true;
  element("status-neu").hidden = true;
  try {
    const [status, briefing] = await Promise.all([
      api<Kontingent>("/api/status"),
      briefingLaden ? api<Briefing>("/api/briefing") : Promise.resolve(null),
    ]);
    if (aktuell !== revision || ladung !== ladeRevision || !benutzer) return;
    if (briefing) {
      ansicht.briefing(briefing);
      ansicht.status("Ihr Briefing ist bereit.");
    }
    element("kontingent").hidden = !status.kontingent_knapp && !status.gesperrt;
    element("kontingent").textContent = status.gesperrt
      ? "Das Übungskontingent ist aufgebraucht. Es kann zurzeit kein Gespräch gestartet werden."
      : "Das Übungskontingent ist bald aufgebraucht.";
    element<HTMLButtonElement>("start").disabled = status.gesperrt || !ansicht.framework();
    if (
      !element("bereit").hidden &&
      (document.activeElement === document.body ||
        document.activeElement?.closest("[hidden], [inert]"))
    ) {
      element(status.gesperrt ? "bereit-titel" : "start").focus();
    }
    element("status-neu").hidden = !status.gesperrt;
  } catch (fehler) {
    if (aktuell !== revision || ladung !== ladeRevision) return;
    if (fehler instanceof ApiFehler && fehler.status === 401) anmeldung(fehler.message);
    else {
      ansicht.status(fehlermeldung(fehler));
      element("status-neu").hidden = false;
    }
  }
}
function bereit(name: string) {
  revision++;
  benutzer = name;
  ansicht.bereit(name);
  void statusLaden();
}
element<HTMLFormElement>("anmeldeformular").addEventListener("submit", (ereignis) => {
  ereignis.preventDefault();
  const knopf = element<HTMLButtonElement>("anmelden");
  if (knopf.disabled) return;
  const aktuell = ++revision;
  knopf.disabled = true;
  knopf.textContent = "Anmelden …";
  element("anmeldefehler").hidden = true;
  const name = element<HTMLInputElement>("name").value;
  const passwort = element<HTMLInputElement>("passwort").value;
  element<HTMLInputElement>("passwort").value = "";
  void api<{ name: string }>("/api/login", { name, passwort })
    .then(
      (antwort) => {
        if (aktuell === revision) bereit(antwort.name);
      },
      (fehler: unknown) => {
        if (aktuell !== revision) return;
        element("anmeldefehler").textContent = fehlermeldung(fehler);
        element("anmeldefehler").hidden = false;
        element("name").setAttribute("aria-describedby", "anmeldefehler");
        element("name").focus();
      },
    )
    .finally(() => {
      knopf.disabled = false;
      knopf.textContent = "Anmelden";
    });
});
element("abmelden").addEventListener("click", () => {
  anmeldung("Sie werden abgemeldet …");
  const aktuell = revision;
  const knopf = element<HTMLButtonElement>("anmelden");
  knopf.disabled = true;
  void api("/api/logout", {})
    .then(
      () => {
        if (aktuell === revision) ansicht.status("Sie sind abgemeldet.");
      },
      (fehler: unknown) => {
        if (aktuell === revision)
          ansicht.status(
            `${fehlermeldung(fehler)} Die lokale Ansicht wurde geschlossen; die Abmeldung beim Server ist nicht bestätigt.`,
          );
      },
    )
    .finally(() => {
      knopf.disabled = false;
    });
});
element("start").addEventListener("click", () => {
  const framework = ansicht.framework();
  if (benutzer && framework && !element<HTMLButtonElement>("start").disabled)
    void gespraech.starten(framework);
});
for (const id of ["beenden", "mikrofon-abbrechen", "briefing-abbrechen", "anwaehlen-abbrechen"])
  element(id).addEventListener("click", () => {
    gespraech.beenden();
  });
for (const prefix of ["briefing", "ergebnis"]) {
  element(`${prefix}-weiter`).addEventListener("click", () => {
    gespraech.ueberspringen();
  });
  element(`${prefix}-pause`).addEventListener("click", () => {
    gespraech.pause();
  });
}
element("fertig").addEventListener("click", () => {
  gespraech.fertig();
});
element("status-neu").addEventListener("click", () => {
  void statusLaden();
});
element("transkript-knopf").addEventListener("click", () => {
  ansicht.schublade(element("transkript").hidden === true);
});
element("transkript-zu").addEventListener("click", () => {
  ansicht.schublade(false);
});
element("transkript").addEventListener("keydown", (event) => {
  if (event.key === "Escape") ansicht.schublade(false);
});
element("pegel-schalter").addEventListener("click", () => {
  // Ein ausgeschalteter AudioContext wird nicht außerhalb der Startgeste erzeugt.
  pegelEin = pegel?.aktivieren(!pegelEin) ?? false;
  pegelKnopf();
});
element("ton").addEventListener("click", () => {
  void gespraech.tonAktivieren();
});
addEventListener("pagehide", () => {
  gespraech.verlassen();
  revision++;
  pegel = null;
});
// Ein aus dem Back/Forward-Cache zurückgekehrter Tab besitzt keine aktive Sitzung.
addEventListener("pageshow", (event) => {
  if (event.persisted) location.reload();
});
const initial = revision;
void api<{ name: string }>("/api/me").then(
  (antwort) => {
    if (initial === revision) bereit(antwort.name);
  },
  (fehler: unknown) => {
    if (initial === revision)
      anmeldung(
        fehler instanceof ApiFehler && fehler.status === 401
          ? "Bitte melden Sie sich an."
          : fehlermeldung(fehler),
      );
  },
);
