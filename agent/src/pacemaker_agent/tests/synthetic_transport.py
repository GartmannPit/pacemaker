"""Datei-basierter Audio-Transport fuer den Synthetic Caller.

Speist vordefinierte WAV-Clips als InputAudioRawFrame-Strom ein, real-time
gepaced -- wie ein echtes Mikrofon liefert. Das ist absichtlich: VAD und
Turn-Detection arbeiten mit demselben Timing wie im Live-Betrieb, und die
Latenzmessung (echte Netzwerk-/Inferenzzeit von Azure) bleibt unverfaelscht,
weil nur das Einspeisen der Aufnahme simuliert wird, nicht die Antwortzeit.

Die Ausgabeseite verwirft Audio, spielt es aber im Echtzeittakt "ab" (siehe
SyntheticOutputTransport), damit Antwortdauer und Textfreigabe wie im Live-Betrieb
verlaufen.
"""

from __future__ import annotations

import asyncio
import math
import time
import wave
from array import array
from collections.abc import Callable
from pathlib import Path

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams

SAMPLE_RATE = 16000  # muss zu den generierten Fixture-WAVs passen (generate_fixtures.py)
CHUNK_MS = 20
TRAILING_SILENCE_SECS = 4.0  # > Smart-Turn-v3-Default stop_secs=3, siehe base_smart_turn.py
_SILENCE_RATIO = 0.05  # wie generate_fixtures: Frame still unter 5 % des lautesten Frames


def _voiced_frames(pcm: bytes, frame_ms: int) -> tuple[list[int], int]:
    samples = array("h", pcm)
    step = SAMPLE_RATE * frame_ms // 1000
    rms = [
        math.sqrt(sum(x * x for x in samples[i : i + step]) / step)
        for i in range(0, len(samples) - step + 1, step)
    ]
    if not rms:
        return [], step
    threshold = max(rms) * _SILENCE_RATIO
    return [i for i, value in enumerate(rms) if value >= threshold], step


def last_voiced_sample(pcm: bytes, frame_ms: int = 10) -> int:
    """Index des Samples, an dem der letzte hoerbare 10-ms-Frame endet."""
    voiced, step = _voiced_frames(pcm, frame_ms)
    return (voiced[-1] + 1) * step if voiced else 0


def voice_onset_secs(wav_path: Path) -> float:
    """Sekunden Stille vor dem ersten hoerbaren Frame eines Clips."""
    with wave.open(str(wav_path), "rb") as wav_file:
        pcm = wav_file.readframes(wav_file.getnframes())
    return first_voiced_sample(pcm) / SAMPLE_RATE


def first_voiced_sample(pcm: bytes, frame_ms: int = 10) -> int:
    """Index des Samples, an dem der erste hoerbare 10-ms-Frame beginnt."""
    voiced, step = _voiced_frames(pcm, frame_ms)
    return voiced[0] * step if voiced else 0


class SyntheticInputTransport(BaseInputTransport):
    """Speist WAV-Clips statt Mikrofon-Hardware ein."""

    def __init__(self, params: TransportParams) -> None:
        super().__init__(params)
        # Echter Yield-Punkt fuer Aufrufer: ein bereits gesetztes asyncio.Event
        # gibt beim .wait() die Kontrolle NICHT an die Event-Loop zurueck --
        # ohne dieses Signal koennte der Feeder-Loop schon Frames pushen,
        # bevor start()/set_transport_ready() ueberhaupt gelaufen ist (dann
        # existiert die interne _audio_in_queue noch nicht).
        self.ready = asyncio.Event()
        # (Beginn, Ende) des hoerbaren Teils des zuletzt eingespeisten Clips, Unix-Zeit --
        # Bezugspunkte fuer vorzeitige Audioausgabe und Barge-in (Testablauf F3/F5).
        self.last_voice_span: tuple[float | None, float | None] = (None, None)

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)
        self.ready.set()

    async def feed_clip(
        self,
        wav_path: Path,
        stop_silence: asyncio.Event | None = None,
        on_voice_end: Callable[[float | None, float | None], None] | None = None,
    ) -> float | None:
        """Speist einen WAV-Clip plus Stille-Nachlauf ein (real-time gepaced).

        Liefert den Zeitpunkt (Unix-Zeit), zu dem das letzte hoerbare Audio des Clips
        eingespeist war -- das Sprechende als Referenz unabhaengig von der VAD.

        `stop_silence` bricht den Stille-Nachlauf ab (Barge-in: der Zwischenruf folgt,
        waehrend die Persona noch spricht). `on_voice_end(start, ende)` meldet den hoerbaren
        Bereich, sobald der Clip eingespeist ist -- vor dem Nachlauf.
        """
        chunk_frames = int(SAMPLE_RATE * CHUNK_MS / 1000)

        with wave.open(str(wav_path), "rb") as wav_file:
            if wav_file.getframerate() != SAMPLE_RATE:
                raise ValueError(
                    f"{wav_path.name}: erwartet {SAMPLE_RATE} Hz, hat "
                    f"{wav_file.getframerate()} Hz -- mit generate_fixtures.py neu erzeugen."
                )
            pcm = wav_file.readframes(wav_file.getnframes())

        speech_end_sample = last_voiced_sample(pcm)
        speech_start_sample = first_voiced_sample(pcm)
        speech_end_ts: float | None = None
        speech_start_ts: float | None = None
        bytes_per_chunk = chunk_frames * 2
        for offset in range(0, len(pcm), bytes_per_chunk):
            data = pcm[offset : offset + bytes_per_chunk]
            pushed_at = time.time()
            await self.push_audio_frame(
                InputAudioRawFrame(audio=data, sample_rate=SAMPLE_RATE, num_channels=1)
            )
            chunk_start = offset // 2
            if speech_start_ts is None and chunk_start + chunk_frames > speech_start_sample:
                speech_start_ts = (
                    pushed_at + max(0, speech_start_sample - chunk_start) / SAMPLE_RATE
                )
            if speech_end_ts is None and chunk_start + chunk_frames >= speech_end_sample:
                speech_end_ts = pushed_at + (speech_end_sample - chunk_start) / SAMPLE_RATE
            await asyncio.sleep(CHUNK_MS / 1000)
        self.last_voice_span = (speech_start_ts, speech_end_ts)
        if on_voice_end is not None:
            on_voice_end(speech_start_ts, speech_end_ts)

        silence_chunk = b"\x00\x00" * chunk_frames  # 16-bit mono Stille
        silent_chunks = int(TRAILING_SILENCE_SECS * 1000 / CHUNK_MS)
        for _ in range(silent_chunks):
            if stop_silence is not None and stop_silence.is_set():
                break
            await self.push_audio_frame(
                InputAudioRawFrame(audio=silence_chunk, sample_rate=SAMPLE_RATE, num_channels=1)
            )
            await asyncio.sleep(CHUNK_MS / 1000)
        return speech_end_ts


class SyntheticOutputTransport(BaseOutputTransport):
    """Verwirft Audio, spielt es aber in Echtzeit "ab" wie ein Lautsprecher.

    Ohne Echtzeit-Takt war der Bot nach Sekundenbruchteilen "fertig", waehrend Pipecat
    den Antworttext weiter im Sprechtempo freigab. Der naechste Clip markierte die
    Antwort dann als unterbrochen und kuerzte sie im Gespraechsverlauf (2026-10-04).
    Die E2E-Messung endet beim ersten Audio-Frame und ist davon unberuehrt.
    """

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        bytes_per_second = frame.sample_rate * frame.num_channels * 2  # 16-bit PCM
        await asyncio.sleep(len(frame.audio) / bytes_per_second)
        return True


class SyntheticTransport(BaseTransport):
    """Transport-Paar fuer den Synthetic Caller: Datei-Audio statt Mikro/Lautsprecher."""

    def __init__(self) -> None:
        super().__init__()
        params = TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        )
        self._input_transport = SyntheticInputTransport(params)
        self._output_transport = SyntheticOutputTransport(params)

    def input(self) -> SyntheticInputTransport:
        return self._input_transport

    def output(self) -> FrameProcessor:
        return self._output_transport
