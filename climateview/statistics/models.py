from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PeriodValue = int | str


@dataclass(frozen=True)
class AnalysisContext:
    """
    Describes the exact chart view being analyzed.
    """

    location: str
    metric: str
    unit: str
    aggregation: str
    start_period: PeriodValue
    end_period: PeriodValue
    period_label: str | None = None

@dataclass(frozen=True)
class DataSchema:
    """
    Describes how the input dataframe is structured.
    """

    period_column: str
    value_column: str

@dataclass(frozen=True)
class DataQualityStatistics:
    """
    Describes the quantity and completeness of the selected data.
    """

    observation_count: int
    missing_count: int
    completeness_percent: float
    first_period: PeriodValue
    last_period: PeriodValue
    expected_observation_count: int | None = None
    duplicate_period_count: int = 0


@dataclass(frozen=True)
class DescriptiveStatistics:
    """
    Basic descriptive statistics for the selected numerical series.
    """

    mean: float
    median: float
    minimum: float
    maximum: float
    standard_deviation: float
    sum: float | None = None


@dataclass(frozen=True)
class ExtremeValue:
    """
    A minimum or maximum value and the period in which it occurred.
    """

    period: PeriodValue
    value: float


@dataclass(frozen=True)
class TrendStatistics:
    """
    Regression-based trend statistics for the selected period.
    """

    slope_per_period: float
    total_fitted_change: float
    direction: str
    statistically_significant: bool
    p_value: float | None = None
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
    r_squared: float | None = None


@dataclass(frozen=True)
class VariabilityStatistics:
    """
    Describes how much values fluctuate around the mean.
    """

    standard_deviation: float
    coefficient_of_variation: float | None
    variability_level: str
    range_value: float
    interquartile_range: float | None = None


@dataclass(frozen=True)
class RecentChangeStatistics:
    """
    Compares a recent portion of the selected series with an earlier baseline.
    """

    baseline_mean: float
    recent_mean: float
    absolute_change: float
    percent_change: float | None
    baseline_period: str
    recent_period: str


@dataclass(frozen=True)
class Insight:
    """
    One verified finding selected for display or LLM summarization.
    """

    insight_type: str
    importance: float
    statement: str
    llm_priority: bool = True
    supporting_values: dict[str, Any] = field(default_factory=dict)
    caveat: str | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """
    Complete output produced by the statistics engine.
    """

    context: AnalysisContext
    data_quality: DataQualityStatistics
    descriptive: DescriptiveStatistics
    trend: TrendStatistics | None
    variability: VariabilityStatistics
    minimum: ExtremeValue
    maximum: ExtremeValue
    recent_change: RecentChangeStatistics | None
    metric_specific: dict[str, Any] = field(default_factory=dict)
    insights: list[Insight] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the complete result into a JSON-serializable dictionary.
        """

        return asdict(self)