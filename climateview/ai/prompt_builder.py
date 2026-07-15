from __future__ import annotations

import json
from typing import Any

from climateview.statistics.models import AnalysisResult


SYSTEM_INSTRUCTIONS = """
You explain climate and environmental statistics to a general audience.

Follow these rules:
- Use only the supplied facts and statistics.
- Do not calculate new statistics.
- Do not infer or speculate about causes.
- Do not claim that a trend is meaningful unless it is marked statistically significant.
- Distinguish long-term trends from recent patterns.
- Include important caveats about variability, missing data, or incomplete periods.
- For precipitation, use neutral wording; higher or lower precipitation is not inherently better.
- Describe statistical significance in plain language.
- Do not mention p-values, R-squared values, standard deviations, or coefficients of variation.
- Mention record minimum and maximum periods only when they help explain the overall pattern.
- Prefer rounded values appropriate for a general audience.
- Write one concise paragraph of approximately 90 to 140 words.
- Do not use headings, bullet points, markdown, or technical notation.
""".strip()

def build_summary_prompt(result: AnalysisResult) -> str:
    """
    Build a compact prompt from verified statistics.

    The LLM receives core statistics and only insights marked as
    llm_priority=True. It does not receive the full underlying time series.
    """

    payload = build_summary_payload(result)

    return (
        "Interpret the following verified analysis of the currently "
        "displayed chart.\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def build_summary_payload(result: AnalysisResult) -> dict[str, Any]:
    """
    Create the structured data supplied to the LLM.
    """

    context = result.context

    payload: dict[str, Any] = {
        "chart_context": {
            "location": context.location,
            "metric": context.metric,
            "unit": context.unit,
            "aggregation": context.aggregation,
            "start_period": context.start_period,
            "end_period": context.end_period,
        },
        "data_quality": {
            "observation_count": result.data_quality.observation_count,
            "completeness_percent": _round_optional(
                result.data_quality.completeness_percent,
                1,
            ),
            "first_period": result.data_quality.first_period,
            "last_period": result.data_quality.last_period,
        },
        "descriptive_statistics": {
            "mean": _round_optional(result.descriptive.mean, 1),
            "minimum": {
                "period": result.minimum.period,
                "value": _round_optional(result.minimum.value, 1),
            },
            "maximum": {
                "period": result.maximum.period,
                "value": _round_optional(result.maximum.value, 1),
            },
        },
        "variability": {
            "level": result.variability.variability_level,
        },
        "priority_insights": [
            _serialize_insight(insight)
            for insight in result.insights
            if insight.llm_priority
        ],
    }

    if result.trend is not None:
        payload["trend"] = {
            "direction": result.trend.direction,
            "statistically_significant": (
                result.trend.statistically_significant
            ),
        }
    if result.recent_change is not None:
        payload["recent_change"] = {
            "baseline_period": result.recent_change.baseline_period,
            "recent_period": result.recent_change.recent_period,
            "baseline_mean": _round_optional(
                result.recent_change.baseline_mean,
                1,
            ),
            "recent_mean": _round_optional(
                result.recent_change.recent_mean,
                1,
            ),
            "absolute_change": _round_optional(
                result.recent_change.absolute_change,
                1,
            ),
            "percent_change": _round_optional(
                result.recent_change.percent_change,
                1,
            ),
        }

    payload["metric_specific"] = _compact_metric_specific(
        result.metric_specific
    )

    return payload


def _serialize_insight(insight: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": insight.insight_type,
        "statement": insight.statement,
    }

    if insight.caveat:
        value["caveat"] = insight.caveat

    return value


def _compact_metric_specific(
    metric_specific: dict[str, Any],
) -> dict[str, Any]:
    """
    Keep only metric-specific values useful for narrative generation.

    Large lists such as every dry and wet year are deliberately excluded.
    """

    compact: dict[str, Any] = {}

    directionality = metric_specific.get("directionality")
    if directionality is not None:
        compact["directionality"] = directionality

    decadal = metric_specific.get("decadal_analysis")
    if isinstance(decadal, dict) and decadal.get("available"):
        compact["decadal_analysis"] = {
            "recent_pattern": decadal.get("recent_pattern"),
            "current_decade_incomplete": decadal.get(
                "current_decade_incomplete"
            ),
            "decades": [
                {
                    "label": decade.get("label"),
                    "mean": _round_optional(decade.get("mean"), 3),
                    "complete": decade.get("complete"),
                }
                for decade in decadal.get("decades", [])
            ],
        }

    seasonality = metric_specific.get("seasonality")
    if isinstance(seasonality, dict) and seasonality.get("available"):
        compact["seasonality"] = {
            "level": seasonality.get("seasonality_level"),
            "wettest_month": seasonality.get("wettest_month"),
            "driest_month": seasonality.get("driest_month"),
            "top_three_month_share_percent": _round_optional(
                seasonality.get("top_three_month_share_percent"),
                1,
            ),
        }

    consecutive_runs = metric_specific.get("consecutive_runs")
    if isinstance(consecutive_runs, dict):
        compact["consecutive_runs"] = consecutive_runs

    return compact


def _round_optional(
    value: float | int | None,
    digits: int,
) -> float | int | None:
    if value is None:
        return None

    return round(value, digits)