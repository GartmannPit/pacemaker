"""Resampelt Eingangsaudio auf die Abtastrate, die ein Audio-LLM (s2s) erwartet.

Hintergrund: Silero VAD und Smart Turn arbeiten mit 16 kHz (Pipeline-Rate), die
Azure-OpenAI-Realtime-API nimmt PCM nur mit 24 kHz an. Der Prozessor sitzt deshalb
hinter dem User-Aggregator (VAD sieht weiter 16 kHz) und direkt vor dem LLM.
Ausgangsseitig resampelt der Output-Transport selbst.
"""

from __future__ import annotations

from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class InputAudioResampler(FrameProcessor):
    def __init__(self, target_sample_rate: int) -> None:
        super().__init__()
        self._target = target_sample_rate
        self._resampler = create_stream_resampler()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame) and frame.sample_rate != self._target:
            audio = await self._resampler.resample(frame.audio, frame.sample_rate, self._target)
            if not audio:
                # Der Stream-Resampler puffert anfangs und liefert dann leere Bytes. Die
                # Realtime-API lehnt leeres Audio als Fehler ab, und Pipecat beendet nach
                # jedem API-Fehler die Empfangsschleife -- leere Frames deshalb verwerfen.
                return
            frame = InputAudioRawFrame(
                audio=audio, sample_rate=self._target, num_channels=frame.num_channels
            )

        await self.push_frame(frame, direction)
