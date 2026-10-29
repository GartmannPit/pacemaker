// Vorläufige Schwelle: RMS > 0,01 (−40 dBFS) für mindestens 60 ms.
// Messpunkt: empfangener Persona-Track im Browser, nicht bestätigte Wiedergabe.
// Kalibrierung mit echten Browsern/Headsets steht für B10 noch aus.
export const RMS_SCHWELLE = 0.01;
export const AUDIO_FENSTER_MS = 60;
export class AudioDetektor {
  private seit: number | null = null;
  private zuletzt: number | null = null;
  private erkannt = false;
  pruefen(rms: number, jetzt: number): boolean {
    if (this.erkannt) return false;
    // Ein gedrosselter Tab belegt keine durchgehend hörbaren 60 ms.
    if (this.zuletzt !== null && jetzt - this.zuletzt > 100) this.seit = null;
    this.zuletzt = jetzt;
    if (!Number.isFinite(rms) || rms <= RMS_SCHWELLE) this.seit = null;
    else {
      this.seit ??= jetzt;
      if (jetzt - this.seit >= AUDIO_FENSTER_MS) {
        this.erkannt = true;
        return true;
      }
    }
    return false;
  }
}
