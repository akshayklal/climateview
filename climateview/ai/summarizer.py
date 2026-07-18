from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI
from openai import OpenAIError
from pydantic import BaseModel, Field, ValidationError

from climateview.statistics.models import AnalysisResult

from .prompt_builder import (
    QUESTION_SYSTEM_INSTRUCTIONS,
    SYSTEM_INSTRUCTIONS,
    build_question_prompt,
    build_summary_prompt,
)

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 1000


class SummaryGenerationError(RuntimeError):
    """
    Raised when an AI interpretation cannot be generated.
    """


@dataclass(frozen=True)
class SummaryResponse:
    """
    Result returned by the AI summarizer.
    """

    text: str
    model: str
    referenced_periods: tuple[str, ...] = ()
    referenced_series: tuple[str, ...] = ()


class _ChartResponse(BaseModel):
    text: str = Field(description="The answer shown to the user.")
    referenced_periods: list[str] = Field(
        description=(
            "Exact individual chart periods explicitly referenced in the "
            "answer, copied from the verified analysis. Use an empty list "
            "for trends, ranges, or periods not present in the analysis."
        )
    )
    referenced_series: list[str] = Field(
        description=(
            "Exact ranked_periods series names used for the answer. Use an "
            "empty list when no ranked series was used."
        )
    )


def summarize_analysis(
    result: AnalysisResult,
    *,
    model: str | None = None,
    api_key: str | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> SummaryResponse:
    """
    Generate a concise interpretation of an AnalysisResult.

    The API key is resolved in this order:

    1. Explicit api_key argument.
    2. OPENAI_API_KEY environment variable.

    The model is resolved in this order:

    1. Explicit model argument.
    2. CLIMATEVIEW_OPENAI_MODEL environment variable.
    3. DEFAULT_MODEL.
    """

    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")

    if not resolved_api_key:
        raise SummaryGenerationError(
            "OPENAI_API_KEY is not configured."
        )

    resolved_model = (
        model
        or os.getenv("CLIMATEVIEW_OPENAI_MODEL")
        or DEFAULT_MODEL
    )

    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be at least 1.")

    prompt = build_summary_prompt(result)
    client = OpenAI(api_key=resolved_api_key)

    try:
        response = client.responses.parse(
            model=resolved_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            reasoning={"effort": "low"},
            max_output_tokens=max_output_tokens,
            text_format=_ChartResponse,
        )
    except (OpenAIError, ValidationError) as exc:
        raise SummaryGenerationError(
            f"OpenAI summary generation failed: {exc}"
        ) from exc

    parsed = response.output_parsed
    summary = parsed.text.strip() if parsed is not None else ""

    if not summary:
        status = getattr(response, "status", None)
        incomplete_details = getattr(response, "incomplete_details", None)

        raise SummaryGenerationError(
            "OpenAI returned no visible summary. "
            f"status={status}, incomplete_details={incomplete_details}"
        )

    return SummaryResponse(
        text=summary,
        model=resolved_model,
        referenced_periods=tuple(parsed.referenced_periods),
        referenced_series=tuple(parsed.referenced_series),
    )

def answer_analysis_question(
    result: AnalysisResult,
    question: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> SummaryResponse:
    """
    Answer a user question using the verified chart analysis.
    """

    cleaned_question = question.strip()

    if not cleaned_question:
        raise ValueError("Question must not be empty.")

    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")

    if not resolved_api_key:
        raise SummaryGenerationError(
            "OPENAI_API_KEY is not configured."
        )

    resolved_model = (
        model
        or os.getenv("CLIMATEVIEW_OPENAI_MODEL")
        or DEFAULT_MODEL
    )

    prompt = build_question_prompt(result, cleaned_question)
    client = OpenAI(api_key=resolved_api_key)

    try:
        response = client.responses.parse(
            model=resolved_model,
            instructions=QUESTION_SYSTEM_INSTRUCTIONS,
            input=prompt,
            reasoning={"effort": "low"},
            max_output_tokens=max_output_tokens,
            text_format=_ChartResponse,
        )
    except (OpenAIError, ValidationError) as exc:
        raise SummaryGenerationError(
            f"OpenAI question answering failed: {exc}"
        ) from exc

    parsed = response.output_parsed
    answer = parsed.text.strip() if parsed is not None else ""

    if not answer:
        status = getattr(response, "status", None)
        incomplete_details = getattr(
            response,
            "incomplete_details",
            None,
        )

        raise SummaryGenerationError(
            "OpenAI returned no visible answer. "
            f"status={status}, "
            f"incomplete_details={incomplete_details}"
        )

    return SummaryResponse(
        text=answer,
        model=resolved_model,
        referenced_periods=tuple(parsed.referenced_periods),
        referenced_series=tuple(parsed.referenced_series),
    )
