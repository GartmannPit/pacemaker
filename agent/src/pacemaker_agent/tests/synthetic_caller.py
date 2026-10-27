"""Synthetic Caller: spielt vordefinierte deutsche Audio-Clips durch die Pipeline
und misst die E2E-Antwortzeit pro Turn -- reproduzierbare Latenzverteilung statt
Handstoppen, beliebig oft wiederholbar fuer belastbare p50/p90-Werte.

    uv run python -m pacemaker_agent.tests.generate_fixtures     # einmalig
    uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30

Robustheitsprobe (echte Aufnahmen, jede in eigener Sitzung, Ergebnisse getrennt ablegen):

    PACEMAKER_RUNS_DIR=experiments/runs/robust uv run python -m \\
        pacemaker_agent.tests.synthetic_caller --fixtures fixtures/robust --clips R01,R02 --fresh

Verdrahtung: build_pipeline_task() haengt Metrik-Collector und Transkript an und
schreibt das Run-Manifest (siehe pipeline.py). Der Synthetic Caller liefert den
Datei-Transport, die Turn-Taktung (naechster Clip erst, wenn der Bot mit seiner
Antwort fertig ist, sonst wuerde eine ueberlappende Einspeisung wie ein Barge-in
wirken) und das Turn-Protokoll mit genau einem Status je eingespieltem Clip
(metrics/turn_ledger.py).

Zusammenhaengendes Gespraech (Testablauf T1): Clips in fester Reihenfolge, eine Sitzung:

    uv run python -m pacemaker_agent.tests.synthetic_caller --fixtures fixtures/robust \\
        --clips R01,R16,R02 --turns 3

Barge-in (Testablauf T2): letzter Clip beginnt BARGE_IN s nach Beginn der Persona-Antwort:

    uv run python -m pacemaker_agent.tests.synthetic_caller --fixtures fixtures/robust \\
        --clips R01,R02,R23 --turns 3 --barge-in 1.0 --repeat 5

Ergebnisse eines Laufs (gleiche run_id):
  experiments/runs/<run_id>.jsonl            Latenz je beantworteter Aeusserung
  experiments/runs/turns/<run_id>.jsonl      Status + Zeitpunkte je angebotener Aeusserung
  experiments/runs/manifests/<run_id>.json   Konfiguration + Bilanz
  experiments/runs/transcripts/<run_id>.jsonl
  experiments/runs/events/<run_id>.json      Sprechintervalle Clip/Persona, Auflegen
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameDirection

from ..metrics.collector import RUNS_DIR
from ..metrics.run_manifest import load_config, load_manifest, new_run_id, update_manifest
from ..metrics.turn_ledger import TurnLedger
from ..pipeline import build_pipeline_task
from ..stacks import STACKS
from .synthetic_transport import SyntheticTransport, voice_onset_secs

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "audio"


# Der Bot gilt erst als fertig, wenn er so lange am Stueck still ist. Antworten kommen in
# Schueben (TTS satzweise, Realtime-Audio in Paketen); die Luecken dazwischen loesen kurz
# BotStoppedSpeaking aus. Ohne Wartezeit startete der naechste Clip mitten in der Antwort
# und wirkte als Barge-in (2026-10-03 bei s2s beobachtet).
BOT_SETTLE_SECS = 1.0

# Pause zwischen zwei Sitzungen. 1,1 s reichten nicht: Azure STT (Tarif F0, eine gleichzeitige
# Verbindung) lehnte die neue Sitzung mit "Quota exceeded" (1007) ab, solange die vorige
# Verbindung noch offen war (T1, 2026-10-08).
SESSION_GAP_SECS = 5.0
# Sitzungen mit Dienstfehler im Turn-Protokoll werden wiederholt (T1 2026-10-11: "Quota
# exceeded" von Azure STT trotz 5 s Pause, Ursache nicht isoliert).
MAX_SERVICE_RETRIES = 3
RETRY_WAIT_SECS = 20.0


class _BotIdleObserver(BaseObserver):
    """Taktgeber fuer den naechsten Clip."""

    def __init__(self) -> None:
        super().__init__()
        self._bot_idle = asyncio.Event()
        self._bot_idle.set()
        # ("start"|"stop", Unix-Zeit) je Sprechintervall der Persona am Ausgabe-Transport
        self.speaking_events: list[tuple[str, float]] = []
        self._seen: set[int] = set()

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        if data.frame.id in self._seen:
            return
        self._seen.add(data.frame.id)
        if isinstance(data.frame, BotStartedSpeakingFrame):
            self.speaking_events.append(("start", time.time()))
            self._bot_idle.clear()
        elif isinstance(data.frame, BotStoppedSpeakingFrame):
            self.speaking_events.append(("stop", time.time()))
            self._bot_idle.set()

    async def wait_bot_settled(self) -> None:
        """Wartet, bis der Bot BOT_SETTLE_SECS am Stueck nicht gesprochen hat."""
        while True:
            await self._bot_idle.wait()
            try:
                await asyncio.wait_for(self._wait_bot_started(), timeout=BOT_SETTLE_SECS)
            except TimeoutError:
                return

    async def _wait_bot_started(self) -> None:
        while self._bot_idle.is_set():
            await asyncio.sleep(0.05)

    async def wait_bot_started_after(self, ts: float, timeout: float) -> float | None:
        """Erster Sprechbeginn der Persona nach `ts`; None bei Zeitueberschreitung."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for kind, t in self.speaking_events:
                if kind == "start" and t > ts:
                    return t
            await asyncio.sleep(0.01)
        return None


def _select_clips(fixtures: Path, ids: list[str] | None) -> list[Path]:
    clips = sorted(fixtures.glob("*.wav"))
    if ids:
        by_stem = {c.stem: c for c in clips}
        missing = [i for i in ids if i not in by_stem]
        if missing:
            raise SystemExit(f"Clips nicht gefunden in {fixtures}: {', '.join(missing)}")
        clips = [by_stem[i] for i in ids]
    if not clips:
        raise SystemExit(
            f"Keine WAV-Clips in {fixtures}. Erst "
            f"`uv run python -m pacemaker_agent.tests.generate_fixtures` laufen lassen."
        )
    return clips


def _clips_sha(clips: list[Path]) -> str:
    h = hashlib.sha256()
    for clip in sorted(set(clips)):
        h.update(clip.name.encode())
        h.update(clip.read_bytes())
    return h.hexdigest()[:12]


def persona_hung_up(run_id: str) -> bool:
    """True, wenn die Persona per Werkzeug `auflegen` regulär beendet hat (Transkript-Ereignis)."""
    path = RUNS_DIR / "transcripts" / f"{run_id}.jsonl"
    if not path.exists():
        return False
    return any(
        row.get("role") == "event" and row.get("text") == "auflegen"
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    )


async def _until(aw, run_task: asyncio.Task) -> bool:
    """Wartet auf `aw`; False, wenn die Pipeline vorher endet (z. B. Persona hat aufgelegt)."""
    waiter = asyncio.ensure_future(aw)
    try:
        done, _ = await asyncio.wait({waiter, run_task}, return_when=asyncio.FIRST_COMPLETED)
        if waiter in done:
            waiter.result()
            return True
        return False
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


async def _session(
    stack: str,
    sequence: list[Path],
    run_id: str,
    manifest_extra: dict,
    barge_in: float | None = None,
) -> dict:
    """Eine Pipeline-Sitzung, die die Clips der Reihe nach einspielt.

    Jeder Clip folgt, wenn die Persona BOT_SETTLE_SECS still ist. Mit `barge_in` wird der
    letzte Clip als Zwischenruf eingespielt: hoerbarer Beginn `barge_in` s nach Beginn der
    Persona-Antwort auf den vorletzten (dessen Stille-Nachlauf wird dafuer abgebrochen).
    Legt die Persona auf, endet die Sitzung; restliche Clips gelten als nicht angeboten.
    """
    transport = SyntheticTransport()
    bot_idle = _BotIdleObserver()
    ledger = TurnLedger()
    task = build_pipeline_task(
        stack,
        transport,
        run_id=run_id,
        extra_observers=[bot_idle, ledger],
        manifest_extra=manifest_extra,
    )

    runner = PipelineRunner()
    run_task = asyncio.create_task(runner.run(task))

    clips_log: list[dict] = []
    ended_by_pipeline_after: int | None = None

    async def feed_one(i: int, clip: Path, stop_silence: asyncio.Event | None) -> None:
        logger.info(f"Turn {i}/{len(sequence)}: {clip.name}")
        ledger.begin(i, clip.name)

        def on_voice_end(start: float | None, end: float | None) -> None:
            clips_log.append({"uid": i, "clip": clip.stem, "voice_start": start, "voice_end": end})

        speech_end = await transport.input().feed_clip(clip, stop_silence, on_voice_end)
        ledger.set_speech_end(i, speech_end)

    async def feed() -> None:
        nonlocal ended_by_pipeline_after
        last = len(sequence)
        stop_silence = asyncio.Event()
        previous: asyncio.Task | None = None
        for i, clip in enumerate(sequence, 1):
            if barge_in is not None and i == last and i > 1:
                # Zwischenruf: hoerbarer Beginn `barge_in` s nach Beginn der Persona-Antwort
                # auf den vorigen Clip. Stille am Clipanfang wird herausgerechnet.
                ref = clips_log[-1]["voice_end"] or time.time()
                started = await bot_idle.wait_bot_started_after(ref, timeout=8.0)
                if started is not None:
                    lead = voice_onset_secs(clip)
                    await asyncio.sleep(max(0.0, started + barge_in - lead - time.time()))
                stop_silence.set()
                if previous is not None:
                    await previous
                await feed_one(i, clip, None)
                break
            if not await _until(bot_idle.wait_bot_settled(), run_task):
                ended_by_pipeline_after = i - 1
                return
            if barge_in is not None and i == last - 1:
                # Vorletzter Clip: Einspeisung laeuft im Hintergrund weiter, damit der
                # Stille-Nachlauf fuer den Zwischenruf abgebrochen werden kann.
                previous = asyncio.create_task(feed_one(i, clip, stop_silence))
                while len(clips_log) < i:
                    await asyncio.sleep(0.01)
                continue
            if not await _until(feed_one(i, clip, None), run_task):
                ended_by_pipeline_after = i
                return
            await asyncio.sleep(0.3)  # kurze Luft, bis Turn-Detection reagiert
        if not await _until(bot_idle.wait_bot_settled(), run_task):  # letzte Antwort
            ended_by_pipeline_after = len(sequence)
            return
        await task.stop_when_done()

    feed_task = None
    failure = None
    try:
        # Auch ein Fehler vor Transport-Bereitschaft muss das Warten beenden.
        if await _until(transport.input().ready.wait(), run_task):
            feed_task = asyncio.create_task(feed())
            await asyncio.gather(feed_task, run_task)
        else:
            await run_task
            ended_by_pipeline_after = 0
    except asyncio.CancelledError:
        failure = "CancelledError"
        raise
    except Exception as exc:
        failure = type(exc).__name__
    finally:
        if feed_task is not None and not feed_task.done():
            feed_task.cancel()
            await asyncio.gather(feed_task, return_exceptions=True)
        if not run_task.done():
            await task.cancel(reason="synthetic_caller_beendet")
            await run_task
        ledger_path, balance = ledger.write(run_id)
        # Legt die Persona vor dem letzten Clip auf, ist das ein reguläres Gesprächsende
        # (Läufe 2026-10-15: in allen vollständigen Sitzungen vor Clip 10).
        hung_up = persona_hung_up(run_id)
        update_manifest(
            run_id,
            finished=datetime.now(UTC).isoformat(),
            harness_error=failure,
            turns_requested=len(sequence),
            result=balance,
            hung_up=hung_up,
            session_complete=failure is None and (balance["offered"] == len(sequence) or hung_up),
        )

    events_dir = RUNS_DIR / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "barge_in_secs": barge_in,
                "clips": clips_log,
                "bot_speaking": bot_idle.speaking_events,
                "ended_by_pipeline_after_clip": ended_by_pipeline_after,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    update_manifest(
        run_id,
        turns_requested=len(sequence),
        result=balance,
        ended_by_pipeline_after_clip=ended_by_pipeline_after,
    )
    _report_balance(balance)
    if ended_by_pipeline_after is not None:
        logger.info(f"Sitzung von der Pipeline beendet nach Clip {ended_by_pipeline_after}")
    logger.info(f"Turn-Protokoll: {ledger_path}")
    service_error = bool((load_manifest(run_id) or {}).get("service_errors")) or any(
        json.loads(line).get("errors")
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return {
        **balance,
        "ended_by_pipeline_after_clip": ended_by_pipeline_after,
        "service_error": service_error,
    }


async def _run(
    stack: str,
    turns: int,
    fixtures: Path,
    ids: list[str] | None,
    fresh: bool,
    barge_in: float | None = None,
    repeat: int = 1,
    continue_after_hangup: bool = False,
    service_retries: bool = True,
) -> list[str]:
    load = load_config()
    if load["load_concurrency"] is not None:
        if fresh or repeat != 1 or continue_after_hangup:
            raise ValueError("Lasttest erlaubt genau eine Sitzung je Anrufer")
        service_retries = False
    clips = _select_clips(fixtures, ids)
    manifest_extra = {
        # ueberschreibt den Default-Fixture-Hash im Manifest: belegt, welche Clips liefen
        "fixtures": fixtures.name,
        "fixtures_sha": _clips_sha(clips),
        "fresh_session": fresh,
        "barge_in_secs": barge_in,
    }
    if not fresh:
        sequence = [clips[i % len(clips)] for i in range(turns)]
        run_ids = []
        for rep_no in range(1, repeat + 1):
            remaining, call_no, offset, retries = sequence, 1, 0, 0
            while remaining:
                run_id = new_run_id(stack)
                extra = {**manifest_extra, "repeat": rep_no, "call": call_no, "clip_offset": offset}
                result = await _session(stack, remaining, run_id, extra, barge_in)
                run_ids.append(run_id)
                await asyncio.sleep(SESSION_GAP_SECS)
                if service_retries and result["service_error"] and retries < MAX_SERVICE_RETRIES:
                    # Dienstfehler (z. B. Azure "Quota exceeded"): Sitzung ist ungueltig und
                    # wird mit neuer run_id wiederholt; die ungueltige bleibt im Protokoll.
                    retries += 1
                    logger.warning(f"Dienstfehler in {run_id} -- Wiederholung {retries}")
                    await asyncio.sleep(RETRY_WAIT_SECS)
                    continue
                ended = result["ended_by_pipeline_after_clip"]
                if not continue_after_hangup or ended is None or ended >= len(remaining):
                    break
                # Persona hat aufgelegt: restliche Clips als "Wiederanruf" in neuer Sitzung
                logger.info(f"Wiederanruf mit {len(remaining) - ended} restlichen Clips")
                remaining, call_no, offset = remaining[ended:], call_no + 1, offset + ended
        return run_ids

    # Jeder Clip in einer eigenen Sitzung: kein gemeinsamer Gespraechsverlauf, keine
    # Wiederholungseffekte (Robustheitsprobe). --turns wird hier ignoriert.
    run_ids = []
    for clip in clips:
        run_id = f"{new_run_id(stack)}-{clip.stem}"
        await _session(stack, [clip], run_id, {**manifest_extra, "clip": clip.stem})
        run_ids.append(run_id)
        await asyncio.sleep(SESSION_GAP_SECS)
    return run_ids


def _report_balance(balance: dict) -> None:
    """Genau ein Status je eingespieltem Clip; alles ausser 'beantwortet' verzerrt die
    Latenzverteilung oder ist ein Ausfall und wird deshalb laut gemeldet."""
    counts = balance["status_counts"]
    summary = " | ".join(f"{k} {v}" for k, v in counts.items() if v) or "leer"
    line = (
        f"Turn-Bilanz: {balance['offered']} angeboten | {summary} | "
        f"LLM-Text {balance['text_delivery']}"
    )
    if counts.get("beantwortet") == balance["offered"]:
        logger.info(line)
    else:
        logger.warning(f"{line} -- Ausfaelle/Abweichungen, siehe Turn-Protokoll")


def main() -> None:
    parser = argparse.ArgumentParser(prog="synthetic-caller")
    parser.add_argument("--stack", default="azure-eu", choices=STACKS)
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument(
        "--fixtures", type=Path, default=FIXTURES, help="Ordner mit 16-kHz-WAV-Clips"
    )
    parser.add_argument(
        "--clips", default=None, help="Kommagetrennte Clip-Namen ohne .wav (Default: alle)"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Jeden Clip in einer eigenen Sitzung abspielen"
    )
    parser.add_argument(
        "--barge-in",
        type=float,
        default=None,
        help="Letzten Clip als Zwischenruf so viele s nach Beginn der Persona-Antwort",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Sitzungen wiederholen")
    parser.add_argument(
        "--continue-after-hangup",
        action="store_true",
        help="Legt die Persona auf, restliche Clips in neuer Sitzung (Wiederanruf) einspielen",
    )
    parser.add_argument(
        "--no-service-retries", action="store_true", help="Dienstfehler nicht wiederholen"
    )
    args = parser.parse_args()

    ids = [c.strip() for c in args.clips.split(",")] if args.clips else None
    run_ids = asyncio.run(
        _run(
            args.stack,
            args.turns,
            args.fixtures,
            ids,
            args.fresh,
            barge_in=args.barge_in,
            repeat=args.repeat,
            continue_after_hangup=args.continue_after_hangup,
            service_retries=not args.no_service_retries,
        )
    )
    logger.info(f"Fertig. Lauf: {', '.join(run_ids)}")
    logger.info("Auswertung: uv run python -m pacemaker_agent.metrics.aggregate")


if __name__ == "__main__":
    main()
