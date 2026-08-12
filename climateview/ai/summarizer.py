from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError

from climateview.statistics.models import AnalysisResult

from .prompt_builder import build_ai_request


DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 1000


class AIGenerationError(RuntimeError):
    """Raised when an AI response cannot be generated."""


@dataclass(frozen=True)
class AnalysisResponse:
    text: str
    model: str
    referenced_periods: tuple[str, ...] = ()
    referenced_series: tuple[str, ...] = ()


class _StructuredResponse(BaseModel):
    text: str = Field(description="The text shown to the user.")
    referenced_periods: list[str] = Field(
        description="Exact individual chart periods mentioned in the text."
    )
    referenced_series: list[str] = Field(
        description="Exact ranked_periods series names used in the text."
    )


def generate_analysis_response(
    result: AnalysisResult,
    question: str | None = None,
    *,
    model: str | None = None,
    api_key: str | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> AnalysisResponse:
    """Generate an automatic chart summary or answer a chart question."""
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_api_key:
        raise AIGenerationError("OPENAI_API_KEY is not configured.")
    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be at least 1.")

    resolved_model = (
        model or os.getenv("CLIMATEVIEW_OPENAI_MODEL") or DEFAULT_MODEL
    )
    instructions, prompt = build_ai_request(result, question)

    try:
        response = OpenAI(api_key=resolved_api_key).responses.parse(
            model=resolved_model,
            instructions=instructions,
            input=prompt,
            reasoning={"effort": "low"},
            max_output_tokens=max_output_tokens,
            text_format=_StructuredResponse,
        )
    except (OpenAIError, ValidationError) as exc:
        raise AIGenerationError(f"OpenAI response generation failed: {exc}") from exc

    parsed = response.output_parsed
    text = parsed.text.strip() if parsed else ""
    if not text:
        raise AIGenerationError(
            "OpenAI returned no visible response. "
            f"status={getattr(response, 'status', None)}, "
            f"incomplete_details={getattr(response, 'incomplete_details', None)}"
        )

    return AnalysisResponse(
        text=text,
        model=resolved_model,
        referenced_periods=tuple(parsed.referenced_periods),
        referenced_series=tuple(parsed.referenced_series),
    )
