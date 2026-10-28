import type { Uhr } from "./herzschlag.ts";

export function offen<T>() {
  let loesen!: (wert: T) => void;
  let ablehnen!: (grund: unknown) => void;
  const promise = new Promise<T>((resolve, reject) => {
    loesen = resolve;
    ablehnen = reject;
  });
  return { promise, loesen, ablehnen };
}
export async function spuelen() {
  for (let i = 0; i < 16; i++) await Promise.resolve();
}
export class TestUhr implements Uhr {
  private zeit = 0;
  private aufgaben = new Map<object, { zeit: number; aufgabe: () => void }>();
  jetzt() {
    return this.zeit;
  }
  setzen(aufgabe: () => void, ms: number) {
    const id = {};
    this.aufgaben.set(id, { zeit: this.zeit + ms, aufgabe });
    return () => {
      this.aufgaben.delete(id);
    };
  }
  async weiter(ms: number) {
    const ziel = this.zeit + ms;
    for (;;) {
      const naechste = [...this.aufgaben].sort((a, b) => a[1].zeit - b[1].zeit)[0];
      if (!naechste || naechste[1].zeit > ziel) break;
      this.zeit = naechste[1].zeit;
      this.aufgaben.delete(naechste[0]);
      naechste[1].aufgabe();
      await spuelen();
    }
    this.zeit = ziel;
    await spuelen();
  }
}
