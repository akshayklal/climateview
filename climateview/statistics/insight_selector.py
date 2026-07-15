from __future__ import annotations

from typing import Any

from .models import (
    AnalysisContext,
    DataQualityStatistics,
    DescriptiveStatistics,
    ExtremeValue,
    Insight,
    RecentChangeStatistics,
    TrendStatistics,
    VariabilityStatistics,
)


MAX_INSIGHTS = 10

LOW_COMPLETENESS_THRESHOLD = 90.0
HIGH_VARIABILITY_IMPORTANCE = 0.90
SIGNIFICANT_TREND_IMPORTANCE = 0.95
STABLE_TREND_IMPORTANCE = 0.75
EXTREME_IMPORTANCE = 0.80
RECENT_CHANGE_IMPORTANCE = 0.85
DATA_QUALITY_IMPORTANCE = 1.00


def select_insights(
    context: AnalysisContext,
    data_quality: DataQualityStatistics,
    descriptive: DescriptiveStatistics,
    trend: TrendStatistics | None,
    variability: VariabilityStatistics,
    minimum: ExtremeValue,
    maximum: ExtremeValue,
    recent_change: RecentChangeStatistics | None,
    metric_specific: dict[str, Any] | None = None,
    max_insights: int = MAX_INSIGHTS,
) -> list[Insight]:
    """
    Select and rank the most useful verified findings.

    This function creates concise factual statements for later display or
    LLM summarization. It does not generate a polished paragraph.
    """

    if max_insights < 1:
        raise ValueError("max_insights must be at least 1.")

    metric_specific = metric_specific or {}

    candidates: list[Insight] = []

    candidates.extend(
        _select_data_quality_insights(
            context=context,
            data_quality=data_quality,
        )
    )

    candidates.extend(
        _select_trend_insights(
            context=context,
            trend=trend,
            variability=variability,
        )
    )

    candidates.extend(
        _select_variability_insights(
            context=context,
            descriptive=descriptive,
            variability=variability,
        )
    )

    candidates.extend(
        _select_extreme_insights(
            context=context,
            minimum=minimum,
            maximum=maximum,
        )
    )

    candidates.extend(
        _select_recent_change_insights(
            context=context,
            recent_change=recent_change,
            variability=variability,
        )
    )

    candidates.extend(
        _select_precipitation_insights(
            context=context,
            metric_specific=metric_specific,
        )
    )

    unique = _deduplicate_insights(candidates)

    ranked = sorted(
        unique,
        key=lambda insight: insight.importance,
        reverse=True,
    )

    return ranked[:max_insights]


def _select_data_quality_insights(
    context: AnalysisContext,
    data_quality: DataQualityStatistics,
) -> list[Insight]:
    insights: list[Insight] = []

    if data_quality.completeness_percent < LOW_COMPLETENESS_THRESHOLD:
        insights.append(
            Insight(
                insight_type="data_completeness",
                importance=DATA_QUALITY_IMPORTANCE,
                statement=(
                    f"The selected {context.metric} record is only "
                    f"{data_quality.completeness_percent:.1f}% complete."
                ),
                supporting_values={
                    "observation_count": data_quality.observation_count,
                    "missing_count": data_quality.missing_count,
                    "completeness_percent": (
                        data_quality.completeness_percent
                    ),
                },
                caveat=(
                    "Interpret trends and extremes cautiously because "
                    "some expected observations are missing."
                ),
            )
        )

    if data_quality.duplicate_period_count > 0:
        insights.append(
            Insight(
                insight_type="duplicate_periods",
                importance=DATA_QUALITY_IMPORTANCE,
                statement=(
                    f"The selected data contains "
                    f"{data_quality.duplicate_period_count} duplicate "
                    f"period entries."
                ),
                llm_priority=False,
                supporting_values={
                    "duplicate_period_count": (
                        data_quality.duplicate_period_count
                    )
                },
                caveat=(
                    "Duplicate periods may affect the analysis unless they "
                    "are expected for this aggregation."
                ),
            )
        )

    return insights


def _select_trend_insights(
    context: AnalysisContext,
    trend: TrendStatistics | None,
    variability: VariabilityStatistics,
) -> list[Insight]:
    if trend is None:
        return []

    unit = context.unit
    aggregation = context.aggregation.replace("_", " ")

    if trend.statistically_significant:
        direction_word = (
            "increased"
            if trend.direction == "increasing"
            else "decreased"
        )

        statement = (
            f"{context.metric.capitalize()} {direction_word} at an "
            f"estimated rate of {abs(trend.slope_per_period):.3g} "
            f"{unit} per {aggregation} over the selected period."
        )

        return [
            Insight(
                insight_type="significant_trend",
                importance=SIGNIFICANT_TREND_IMPORTANCE,
                statement=statement,
                supporting_values={
                    "slope_per_period": trend.slope_per_period,
                    "total_fitted_change": trend.total_fitted_change,
                    "p_value": trend.p_value,
                    "r_squared": trend.r_squared,
                    "direction": trend.direction,
                },
            )
        ]

    caveat = None

    if variability.variability_level == "high":
        caveat = (
            "The fitted change is small relative to normal variation."
        )

    return [
        Insight(
            insight_type="non_significant_trend",
            importance=STABLE_TREND_IMPORTANCE,
            statement=(
                f"The fitted long-term {context.metric} trend is small "
                f"and not statistically significant."
            ),
            supporting_values={
                "slope_per_period": trend.slope_per_period,
                "total_fitted_change": trend.total_fitted_change,
                "p_value": trend.p_value,
                "r_squared": trend.r_squared,
            },
            caveat=caveat,
        )
    ]


def _select_variability_insights(
    context: AnalysisContext,
    descriptive: DescriptiveStatistics,
    variability: VariabilityStatistics,
) -> list[Insight]:
    if variability.variability_level != "high":
        return []

    return [
        Insight(
            insight_type="high_variability",
            importance=HIGH_VARIABILITY_IMPORTANCE,
            statement=(
                f"{context.metric.capitalize()} varies substantially "
                f"from one {context.aggregation.replace('_', ' ')} "
                f"to another."
            ),
            supporting_values={
                "mean": descriptive.mean,
                "standard_deviation": variability.standard_deviation,
                "coefficient_of_variation": (
                    variability.coefficient_of_variation
                ),
                "range": variability.range_value,
            },
        )
    ]


def _select_extreme_insights(
    context: AnalysisContext,
    minimum: ExtremeValue,
    maximum: ExtremeValue,
) -> list[Insight]:
    metric = context.metric.lower()
    unit = context.unit

    if metric == "precipitation":
        minimum_label = "driest"
        maximum_label = "wettest"
    elif metric in {"pm2.5", "ozone", "air_quality"}:
        minimum_label = "lowest"
        maximum_label = "highest"
    elif metric in {
        "temperature",
        "minimum_temperature",
        "maximum_temperature",
        "tmin",
        "tmax",
    }:
        minimum_label = "coolest"
        maximum_label = "warmest"
    else:
        minimum_label = "lowest"
        maximum_label = "highest"

    return [
        Insight(
            insight_type="minimum_extreme",
            importance=EXTREME_IMPORTANCE,
            statement=(
                f"The {minimum_label} period was {minimum.period}, "
                f"with {minimum.value:.3g} {unit}."
            ),
            llm_priority=False,
            supporting_values={
                "period": minimum.period,
                "value": minimum.value,
            },
        ),
        Insight(
            insight_type="maximum_extreme",
            importance=EXTREME_IMPORTANCE,
            statement=(
                f"The {maximum_label} period was {maximum.period}, "
                f"with {maximum.value:.3g} {unit}."
            ),
            llm_priority=False,
            supporting_values={
                "period": maximum.period,
                "value": maximum.value,
            },
        ),
    ]


def _select_recent_change_insights(
    context: AnalysisContext,
    recent_change: RecentChangeStatistics | None,
    variability: VariabilityStatistics,
) -> list[Insight]:
    if recent_change is None:
        return []

    if recent_change.percent_change is None:
        return []

    change_percent = recent_change.percent_change

    if abs(change_percent) < 5.0:
        return []

    direction = "higher" if change_percent > 0 else "lower"

    caveat = None

    if variability.variability_level == "high":
        caveat = (
            "The difference should be interpreted alongside the series' "
            "substantial natural variability."
        )

    return [
        Insight(
            insight_type="recent_change",
            importance=RECENT_CHANGE_IMPORTANCE,
            statement=(
                f"The recent period ({recent_change.recent_period}) "
                f"averaged {abs(change_percent):.1f}% {direction} than "
                f"the earlier baseline "
                f"({recent_change.baseline_period})."
            ),
            supporting_values={
                "baseline_mean": recent_change.baseline_mean,
                "recent_mean": recent_change.recent_mean,
                "absolute_change": recent_change.absolute_change,
                "percent_change": recent_change.percent_change,
            },
            caveat=caveat,
        )
    ]


def _select_precipitation_insights(
    context: AnalysisContext,
    metric_specific: dict[str, Any],
) -> list[Insight]:
    if context.metric.lower() != "precipitation":
        return []

    insights: list[Insight] = []

    decadal = metric_specific.get("decadal_analysis")

    if isinstance(decadal, dict) and decadal.get("available"):
        recent_pattern = decadal.get("recent_pattern", {})
        direction = recent_pattern.get("direction")
        consecutive_declines = recent_pattern.get(
            "consecutive_declines",
            0,
        )
        consecutive_increases = recent_pattern.get(
            "consecutive_increases",
            0,
        )

        if direction == "declining" and consecutive_declines >= 2:
            insights.append(
                Insight(
                    insight_type="recent_decadal_decline",
                    importance=0.88,
                    statement=(
                        f"Average precipitation declined in successive decades, "
                        f"from the {recent_pattern.get('start_decade')} "
                        f"to the {recent_pattern.get('end_decade')}."
                    ),
                    supporting_values={
                        "consecutive_declines": consecutive_declines,
                        "start_decade": recent_pattern.get(
                            "start_decade"
                        ),
                        "end_decade": recent_pattern.get(
                            "end_decade"
                        ),
                    },
                    caveat=(
                        "This is a recent decadal pattern and does not by "
                        "itself establish a sustained long-term climate "
                        "trend."
                    ),
                )
            )

        elif direction == "increasing" and consecutive_increases >= 2:
            insights.append(
                Insight(
                    insight_type="recent_decadal_increase",
                    importance=0.88,
                    statement=(
                        "Average precipitation increased across the most "
                        f"recent {consecutive_increases + 1} complete "
                        "decades."
                    ),
                    supporting_values={
                        "consecutive_increases": consecutive_increases,
                        "start_decade": recent_pattern.get(
                            "start_decade"
                        ),
                        "end_decade": recent_pattern.get(
                            "end_decade"
                        ),
                    },
                    caveat=(
                        "This is a recent decadal pattern and does not by "
                        "itself establish a sustained long-term climate "
                        "trend."
                    ),
                )
            )

        if decadal.get("current_decade_incomplete"):
            insights.append(
                Insight(
                    insight_type="incomplete_current_decade",
                    importance=0.92,
                    statement=(
                        "The current decade is incomplete and should not "
                        "be compared directly with complete decades."
                    ),
                    supporting_values={},
                )
            )

    seasonality = metric_specific.get("seasonality")

    if isinstance(seasonality, dict) and seasonality.get("available"):
        level = seasonality.get("seasonality_level")

        if level == "strong":
            wettest_month = seasonality.get("wettest_month", {})
            top_share = seasonality.get(
                "top_three_month_share_percent"
            )

            statement = (
                "Precipitation is strongly seasonal, with a large share "
                "of the annual total concentrated in a few months."
            )

            insights.append(
                Insight(
                    insight_type="strong_seasonality",
                    importance=0.90,
                    statement=statement,
                    supporting_values={
                        "wettest_month": wettest_month,
                        "top_three_month_share_percent": top_share,
                        "concentration_index": seasonality.get(
                            "concentration_index"
                        ),
                    },
                )
            )

    return insights


def _deduplicate_insights(
    insights: list[Insight],
) -> list[Insight]:
    """
    Keep the highest-priority insight for each insight type.
    """

    by_type: dict[str, Insight] = {}

    for insight in insights:
        existing = by_type.get(insight.insight_type)

        if existing is None or insight.importance > existing.importance:
            by_type[insight.insight_type] = insight

    return list(by_type.values())