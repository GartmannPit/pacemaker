"""Pipecat-Pipeline-Aufbau. Stack-unabhaengig: bekommt fertige STT/LLM/TTS-Objekte."""

from __future__ import annotations

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

from .personas.kaltakquise_head_of_ops import SYSTEM_PROMPT
from .stacks import build_stack


def build_pipeline_task(stack_name: str, transport) -> PipelineTask:
    services = build_stack(stack_name)

    context = OpenAILLMContext(messages=[{"role": "system", "content": SYSTEM_PROMPT}])
    context_aggregator = services.llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            services.stt,
            context_aggregator.user(),
            services.llm,
            services.tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    return PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,  # Barge-in / Unterbrechbarkeit
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )
