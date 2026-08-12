from __future__ import annotations

import json
from typing import Any

from climateview.statistics.models import AnalysisResult, ExtremeValue


COMMON_INSTRUCTIONS = """
Use only the supplied climate or environmental statistics.
- Do not calculate new statistics, invent facts, or speculate about causes.
- Distinguish observed patterns from statistically significant trends.
- Do not claim causation from correlation or time-series patterns.
- For precipitation, use neutral wording; higher or lower is not inherently better.
- Describe statistical significance in plain language without mentioning p-values, R-squared values, standard deviations, or coefficients of variation.
- Treat chart_context.period_semantics as authoritative.
- An observation count is the number of plotted periods with values, not proof that the periods or record are complete. Never describe completeness unless an explicit within-period measurement is supplied.
- Decade values such as 2020s are bucket labels, not record endpoints. Do not infer missing years or completeness from them.
- Use plain language without headings, bullets, markdown, or technical notation.
""".strip()

SUMMARY_INSTRUCTIONS = COMMON_INSTRUCTIONS + """

Write one concise paragraph of approximately 90 to 140 words for a general audience.
Mention extremes only when they help explain the overall pattern, and include important caveats.
Return empty referenced_periods and referenced_series lists.
"""

QUESTION_INSTRUCTIONS = COMMON_INSTRUCTIONS + """

Answer the user's question concisely, usually in 60 to 130 words. If the supplied data cannot answer it, say so clearly.
In referenced_periods, include only exact individual chart periods explicitly mentioned in the answer, copied from the analysis. Do not include ranges.
In referenced_series, include exact ranked_periods series names used in the answer.
"""


def build_ai_request(
    result: AnalysisResult,
    question: str | None = None,
) -> tuple[str, str]:
    """Return instructions and a grounded prompt for a summary or question."""
    payload = json.dumps(
        build_summary_payload(result),
        indent=2,
        ensure_ascii=False,
    )

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

    payload: dict[str, Any] = {
        "chart_context": {
            "location": context.location,
            "metric": context.metric,
            "unit": context.unit,
            "aggregation": aggregation,
            "start_period": context.start_period,
            "end_period": context.end_period,
            "period_semantics": _period_semantics(aggregation),
        },
        "data_quality": {
            "observation_count": result.data_quality.observation_count,
            "observation_count_scope": (
                "Aggregated chart periods with valid values; this does not "
                "establish that each period is complete."
            ),
            "first_period": period(result.data_quality.first_period),
            "last_period": period(result.data_quality.last_period),
        },
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
        payload["recent_change"] = {
            "baseline_period": period(change.baseline_period),
            "recent_period": period(change.recent_period),
            "baseline_mean": _round(change.baseline_mean, 1),
            "recent_mean": _round(change.recent_mean, 1),
            "absolute_change": _round(change.absolute_change, 1),
            "percent_change": _round(change.percent_change, 1),
        }

    metric_specific = _compact_metric_specific(result.metric_specific)
    if metric_specific:
        payload["metric_specific"] = metric_specific

    return payload


def _serialize_extreme(extreme: ExtremeValue, format_period) -> dict[str, Any]:
    return {
        "period": format_period(extreme.period),
        "value": _round(extreme.value, 1),
    }


def _period_semantics(aggregation: str) -> dict[str, Any]:
    if aggregation.strip().lower() in {"decade", "decadal"}:
        return {
            "period_type": "decade_bucket",
            "label_meaning": (
                "2020s labels the decade bucket beginning in 2020; it is "
                "not the final source-data year."
            ),
            "within_bucket_completeness_known": False,
        }
    return {
        "period_type": "aggregated_chart_period",
        "within_period_completeness_known": False,
    }


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

    if "directionality" in values:
        compact["directionality"] = values["directionality"]

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
