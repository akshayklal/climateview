from __future__ import annotations

import json
from typing import Any

from climateview.statistics.models import AnalysisResult, ExtremeValue


COMMON_INSTRUCTIONS = """
Use only the supplied climate or environmental statistics.
- Do not calculate statistics, invent facts, infer causes, or turn an observed pattern into a clear trend unless the analysis marks it statistically significant.
- For precipitation, use neutral wording; higher or lower is not inherently better.
- Describe significance in ordinary language such as "a clear long-term rise" or "no clear long-term change." Do not mention statistical jargon or generic data caveats.
- Treat any chart_context.period_note as authoritative; decade labels such as 2020s are buckets, not record endpoints.
- Use plain language without headings, bullets, markdown, or technical notation.
- Use chart_context.metric instead of a technical acronym. Avoid terms such as baseline, variability, descriptive statistics, and absolute change; say what changed and which years were compared.
- For temperature, describe changes in degrees Fahrenheit and never as a percentage.
- Use at most one verified chart_findings observation when it adds useful context.
- referenced_periods must contain only exact individual periods explicitly mentioned in the response, copied from the analysis; never include ranges. referenced_series must contain the corresponding exact ranked_periods series names.
""".strip()

SUMMARY_INSTRUCTIONS = COMMON_INSTRUCTIONS + """

Write three or four short sentences totaling approximately 70 to 110 words for a general audience.
Lead with the clearest long-term takeaway for the location. Then give one concrete comparison in familiar language. Mention an extreme, seasonal feature, or recent pattern only when it makes the takeaway more useful. Omit secondary statistics and generic caveats.
Include no more than three referenced_periods.
"""

QUESTION_INSTRUCTIONS = COMMON_INSTRUCTIONS + """

Answer the user's question directly in plain language, usually in 40 to 100 words. If the supplied data cannot answer it, say so clearly.
"""


def build_ai_request(
    result: AnalysisResult,
    question: str | None = None,
) -> tuple[str, str]:
    """Return instructions and a grounded prompt for a summary or question."""
    payload = json.dumps(build_summary_payload(result), ensure_ascii=False)

    if question is None:
        prompt = (
            "Interpret this verified analysis of the displayed chart.\n\n"
            f"{payload}"
        )
        return SUMMARY_INSTRUCTIONS, prompt

    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("Question must not be empty.")

    prompt = (
        "Answer the user's question about the displayed chart.\n\n"
        f"Verified chart analysis:\n{payload}\n\n"
        f"User question:\n{cleaned_question}"
    )
    return QUESTION_INSTRUCTIONS, prompt


def build_summary_payload(result: AnalysisResult) -> dict[str, Any]:
    """Select and format the verified statistics supplied to the model."""
    context = result.context
    aggregation = context.aggregation

    def period(value: Any) -> Any:
        return _format_period(value, aggregation)

    chart_context = {
        "location": context.location,
        "metric": context.metric,
        "unit": context.unit,
        "aggregation": aggregation,
        "start_period": context.start_period,
        "end_period": context.end_period,
    }
    period_note = _period_note(aggregation)
    if period_note:
        chart_context["period_note"] = period_note
    first_period = period(result.data_quality.first_period)
    last_period = period(result.data_quality.last_period)
    if period_note or (
        first_period != context.start_period or last_period != context.end_period
    ):
        chart_context["data_period"] = [first_period, last_period]

    payload: dict[str, Any] = {
        "chart_context": chart_context,
        "descriptive_statistics": {
            "mean": _round(result.descriptive.mean, 1),
            "minimum": _serialize_extreme(result.minimum, period),
            "maximum": _serialize_extreme(result.maximum, period),
        },
        "ranked_periods": {
            label: {
                direction: [
                    _serialize_extreme(item, period)
                    for item in items
                ]
                for direction, items in ranking.items()
            }
            for label, ranking in result.rankings.items()
        },
        "variability": result.variability.variability_level,
    }

    if result.trend:
        payload["trend"] = {
            "direction": result.trend.direction,
            "statistically_significant": result.trend.statistically_significant,
        }

    if result.recent_change:
        change = result.recent_change
        recent_change = {
            "baseline_period": period(change.baseline_period),
            "recent_period": period(change.recent_period),
            "baseline_mean": _round(change.baseline_mean, 1),
            "recent_mean": _round(change.recent_mean, 1),
            "absolute_change": _round(change.absolute_change, 1),
        }
        if "temperature" not in context.metric.lower():
            recent_change["percent_change"] = _round(
                change.percent_change,
                1,
            )
        payload["recent_change"] = recent_change

    metric_specific = _compact_metric_specific(result.metric_specific)
    if metric_specific:
        payload["metric_specific"] = metric_specific

    if result.noteworthy_findings:
        payload["chart_findings"] = result.noteworthy_findings

    return payload


def _serialize_extreme(extreme: ExtremeValue, format_period) -> dict[str, Any]:
    return {
        "period": format_period(extreme.period),
        "value": _round(extreme.value, 1),
    }


def _period_note(aggregation: str) -> str | None:
    if aggregation.strip().lower() in {"decade", "decadal"}:
        return "Labels such as 2020s are decade buckets, not record endpoints."
    return None


def _format_period(value: Any, aggregation: str) -> Any:
    if aggregation.strip().lower() not in {"decade", "decadal"}:
        return value

    if isinstance(value, (int, float)) and float(value).is_integer():
        return f"{int(value)}s"

    parts = str(value).split("–")
    if all(part.isdigit() for part in parts):
        return "–".join(f"{part}s" for part in parts)
    return value


def _compact_metric_specific(values: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}

    decadal = values.get("decadal_analysis")
    if decadal and decadal.get("available"):
        compact["decadal_analysis"] = {
            "recent_pattern": decadal.get("recent_pattern"),
            "current_decade_incomplete": decadal.get(
                "current_decade_incomplete"
            ),
            "decades": [
                {
                    "label": decade["label"],
                    "mean": _round(decade["mean"], 3),
                    "complete": decade["complete"],
                }
                for decade in decadal.get("decades", [])
            ],
        }

    seasonality = values.get("seasonality")
    if seasonality and seasonality.get("available"):
        compact["seasonality"] = {
            "level": seasonality.get("seasonality_level"),
            "wettest_month": seasonality.get("wettest_month"),
            "driest_month": seasonality.get("driest_month"),
            "top_three_month_share_percent": _round(
                seasonality.get("top_three_month_share_percent"),
                1,
            ),
        }

    if isinstance(values.get("consecutive_runs"), dict):
        compact["consecutive_runs"] = values["consecutive_runs"]

    return compact


def _round(value: float | int | None, digits: int) -> float | int | None:
    return None if value is None else round(value, digits)
