import type { Uhr } from "./herzschlag.ts";

// Absolute Fristen verhindern Drift bei gedrosselten Hintergrund-Tabs.
export class Countdown {
  private stopTimer = () => {};
  private rest: number;
  private frist: number;
  private aktiv = true;
  private pausiert = false;
  private fuenf = false;
  private readonly uhr: Uhr;
  private readonly tick: (sekunden: number, pause: boolean, ansage: boolean) => void;
  private readonly fertig: () => void;
  private readonly pauseFrist: (() => void) | undefined;

  constructor(
    uhr: Uhr,
    sekunden: number,
    tick: (sekunden: number, pause: boolean, ansage: boolean) => void,
    fertig: () => void,
    pauseFrist?: () => void,
  ) {
    this.uhr = uhr;
    this.rest = sekunden * 1000;
    this.frist = uhr.jetzt() + this.rest;
    this.tick = tick;
    this.fertig = fertig;
    this.pauseFrist = pauseFrist;
    tick(sekunden, false, true);
    this.planen();
  }
  private planen() {
    if (!this.aktiv || this.pausiert) return;
    const rest = Math.max(0, this.frist - this.uhr.jetzt());
    if (rest === 0) {
      this.stop();
      this.fertig();
      return;
    }
    const sekunden = Math.ceil(rest / 1000);
    const ansage = sekunden <= 5 && !this.fuenf;
    if (ansage) this.fuenf = true;
    this.tick(sekunden, false, ansage);
    this.stopTimer = this.uhr.setzen(
      () => {
        this.planen();
      },
      Math.min(rest, 250),
    );
  }
  umschalten() {
    if (!this.aktiv) return;
    this.stopTimer();
    if (this.pausiert) {
      this.pausiert = false;
      this.frist = this.uhr.jetzt() + this.rest;
      this.planen();
    } else {
      this.rest = Math.max(0, this.frist - this.uhr.jetzt());
      this.pausiert = true;
      this.tick(Math.ceil(this.rest / 1000), true, false);
      if (this.pauseFrist)
        this.stopTimer = this.uhr.setzen(() => {
          this.stop();
          this.pauseFrist?.();
        }, 300000);
    }
  }
  stop() {
    this.aktiv = false;
    this.stopTimer();
  }
}
