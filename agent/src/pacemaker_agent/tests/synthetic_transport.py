"""Datei-basierter Audio-Transport fuer den Synthetic Caller.

Speist vordefinierte WAV-Clips als InputAudioRawFrame-Strom ein, real-time
gepaced -- wie ein echtes Mikrofon liefert. Das ist absichtlich: VAD und
Turn-Detection arbeiten mit demselben Timing wie im Live-Betrieb, und die
Latenzmessung (echte Netzwerk-/Inferenzzeit von Azure) bleibt unverfaelscht,
weil nur das Einspeisen der Aufnahme simuliert wird, nicht die Antwortzeit.

Die Ausgabeseite verwirft Audio (kein echtes Abspielen noetig) -- gezaehlt
wird nur das Timing der Frames, das steuert bereits BaseOutputTransport
(_bot_started_speaking / _bot_stopped_speaking) unabhaengig davon, ob
write_audio_frame irgendwohin schreibt.
"""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams

SAMPLE_RATE = 16000  # muss zu den generierten Fixture-WAVs passen (generate_fixtures.py)
CHUNK_MS = 20
TRAILING_SILENCE_SECS = 4.0  # > Smart-Turn-v3-Default stop_secs=3, siehe base_smart_turn.py


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

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)
        self.ready.set()

    async def feed_clip(self, wav_path: Path) -> None:
        """Speist einen WAV-Clip plus Stille-Nachlauf ein (real-time gepaced)."""
        chunk_frames = int(SAMPLE_RATE * CHUNK_MS / 1000)

        with wave.open(str(wav_path), "rb") as wav_file:
            if wav_file.getframerate() != SAMPLE_RATE:
                raise ValueError(
                    f"{wav_path.name}: erwartet {SAMPLE_RATE} Hz, hat "
                    f"{wav_file.getframerate()} Hz -- mit generate_fixtures.py neu erzeugen."
                )
            data = wav_file.readframes(chunk_frames)
            while data:
                await self.push_audio_frame(
                    InputAudioRawFrame(audio=data, sample_rate=SAMPLE_RATE, num_channels=1)
                )
                await asyncio.sleep(CHUNK_MS / 1000)
                data = wav_file.readframes(chunk_frames)

        silence_chunk = b"\x00\x00" * chunk_frames  # 16-bit mono Stille
        silent_chunks = int(TRAILING_SILENCE_SECS * 1000 / CHUNK_MS)
        for _ in range(silent_chunks):
            await self.push_audio_frame(
                InputAudioRawFrame(audio=silence_chunk, sample_rate=SAMPLE_RATE, num_channels=1)
            )
            await asyncio.sleep(CHUNK_MS / 1000)


class SyntheticOutputTransport(BaseOutputTransport):
    """Verwirft Audio -- nur Frame-Timing zaehlt fuer die Latenzmessung."""

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
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
