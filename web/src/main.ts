import "./style.css";
import { api, ApiFehler, fehlermeldung } from "./api.ts";
import type { Kontingent, StartAntwort } from "./api.ts";
import { Ansicht, element } from "./ansicht.ts";
import { browserVerbindung, Gespraech, herzschlagStarten, systemUhr } from "./gespraech.ts";
import { PEGEL_AKTIV, pegelStarten } from "./pegel.ts";
import type { Pegel } from "./pegel.ts";

const ansicht = new Ansicht();
const audio = element<HTMLAudioElement>("audio");
let benutzer = "";
let revision = 0;
let pegel: Pegel | null = null;
let pegelEin = PEGEL_AKTIV && new URLSearchParams(location.search).get("pegel") !== "0";
let tonRevision = 0;
let tonGesperrt = false;

function tonBlockiert(blockiert: boolean) {
  tonGesperrt = blockiert;
  element("ton").hidden = !blockiert;
}
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
  tonRevision++;
  tonBlockiert(false);
  pegel = null;
  element<HTMLInputElement>("passwort").value = "";
  element("anmeldefehler").hidden = true;
  element("name").removeAttribute("aria-describedby");
  ansicht.anmeldung(meldung);
}
const gespraech = new Gespraech<MediaStream>({
  uhr: systemUhr,
  analyse() {
    tonRevision++;
    tonBlockiert(false);
    pegelEin = PEGEL_AKTIV && new URLSearchParams(location.search).get("pegel") !== "0";
    element<HTMLButtonElement>("pegel-schalter").disabled = !pegelEin;
    pegelKnopf();
    pegel = pegelStarten(
      element<HTMLCanvasElement>("ringe"),
      (e, b) => {
        ansicht.pegel(e, b);
      },
      (aktiv) => {
        element("pegel-status").textContent = aktiv
          ? "Eigener Mikrofonpegel aktiv"
          : "Pegelanzeige nicht aktiv; das Gespräch ist davon unabhängig.";
      },
    );
    return pegel;
  },
  mikrofon: () => navigator.mediaDevices.getUserMedia({ audio: true }),
  peer: (stream, analyse, callbacks) =>
    browserVerbindung(stream, analyse, audio, { ...callbacks, tonBlockiert }),
  starten: (sdp) => api<StartAntwort>("/api/session", { sdp }, 25000),
  beenden: (ref) => api("/api/end", { session_ref: ref }),
  herz: (ref, ende) => herzschlagStarten(ref, ende),
  beacon: (ref) => {
    navigator.sendBeacon(
      "/api/end",
      new Blob([JSON.stringify({ session_ref: ref, grund: "tab" })], { type: "application/json" }),
    );
  },
  zustand(wert) {
    ansicht.aktualisieren(wert);
    if (wert.phase === "gespraech") element("ton").hidden = !tonGesperrt;
    if (wert.phase === "beendet") {
      tonRevision++;
      tonBlockiert(false);
      pegel = null;
    }
  },
  transkript: (rolle, delta) => {
    ansicht.transkript(rolle, delta);
  },
  leeren: () => {
    ansicht.leeren();
  },
  abgemeldet: anmeldung,
});

async function statusLaden() {
  const aktuell = revision;
  element<HTMLButtonElement>("start").disabled = true;
  element("status-neu").hidden = true;
  try {
    const status = await api<Kontingent>("/api/status");
    if (aktuell !== revision || !benutzer) return;
    element("kontingent").hidden = !status.kontingent_knapp && !status.gesperrt;
    element("kontingent").textContent = status.gesperrt
      ? "Das Übungskontingent ist aufgebraucht. Es kann zurzeit kein Gespräch gestartet werden."
      : "Das Übungskontingent ist bald aufgebraucht.";
    element<HTMLButtonElement>("start").disabled = status.gesperrt;
    element("status-neu").hidden = !status.gesperrt;
  } catch (fehler) {
    if (aktuell !== revision) return;
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
  if (benutzer) void gespraech.starten();
});
element("beenden").addEventListener("click", () => {
  gespraech.beenden();
});
element("neustart").addEventListener("click", () => {
  if (benutzer) bereit(benutzer);
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
  const aktuell = tonRevision;
  void audio.play().then(
    () => {
      if (aktuell === tonRevision) tonBlockiert(false);
    },
    () => {
      if (aktuell === tonRevision)
        ansicht.status(
          "Die Wiedergabe ist noch blockiert. Bitte prüfen Sie die Audiofreigabe Ihres Browsers und wählen Sie erneut „Ton aktivieren“.",
        );
    },
  );
});
addEventListener("pagehide", () => {
  gespraech.verlassen();
  ansicht.stop();
  revision++;
  tonRevision++;
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
