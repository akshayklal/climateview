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

@dataclass(frozen=True)
class DataSchema:
    """
    Describes how the input dataframe is structured.
    """

    period_column: str
    value_column: str
    ranked_value_columns: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class DataQualityStatistics:
    """Describes the valid periods in the selected chart data."""

    observation_count: int
    first_period: PeriodValue
    last_period: PeriodValue


@dataclass(frozen=True)
class DescriptiveStatistics:
    """Describes the average value of the selected series."""

    mean: float


@dataclass(frozen=True)
class ExtremeValue:
    """
    A minimum or maximum value and the period in which it occurred.
    """

    period: PeriodValue
    value: float


@dataclass(frozen=True)
class TrendStatistics:
    """Describes the direction and significance of a linear trend."""

    direction: str
    statistically_significant: bool
    slope: float | None = None


@dataclass(frozen=True)
class VariabilityStatistics:
    """Broadly classifies how much values fluctuate around the mean."""

    variability_level: str


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
class PeriodComparisonStatistics:
    """Compares fixed-size periods at the beginning and end of a series."""

    baseline_mean: float
    recent_mean: float
    absolute_change: float
    percent_change: float | None
    baseline_period: str
    recent_period: str
    period_size: int


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
    rankings: dict[str, dict[str, list[ExtremeValue]]] = field(
        default_factory=dict
    )
    metric_specific: dict[str, Any] = field(default_factory=dict)
    noteworthy_findings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the complete result into a JSON-serializable dictionary.
        """

        return asdict(self)
