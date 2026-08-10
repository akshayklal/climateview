import numpy as np
import pandas as pd


HIGHLIGHT_COLOR = "#f97316"
HORIZONTAL_LEGEND = {
    "orientation": "h",
    "yanchor": "top",
    "y": -0.20,
    "xanchor": "center",
    "x": 0.5,
}


def apply_standard_layout(
    figure,
    *,
    x_title,
    height,
    margins,
    **layout_options,
):
    """Apply presentation shared by ClimateView time-series charts."""
    figure.update_layout(
        xaxis_title=x_title,
        height=height,
        margin=margins,
        hovermode="x unified",
        legend=HORIZONTAL_LEGEND,
        **layout_options,
    )
    figure.update_xaxes(showgrid=False)


def calculate_linear_trend(x_values, y_values):
    """Return a linear slope and fitted values for numeric x/y data."""
    trend_data = pd.DataFrame(
        {
            "x": x_values,
            "y": y_values,
        }
    ).dropna()

    if len(trend_data) < 2:
        return None, None

    slope, intercept = np.polyfit(
        trend_data["x"],
        trend_data["y"],
        1,
    )
    fitted_values = slope * x_values + intercept

    return float(slope), fitted_values


def select_referenced_periods(df, x_col, references):
    """Return chart rows whose x value exactly matches an AI reference."""
    if df.empty or not references:
        return df.iloc[0:0]

    normalized_references = {
        str(reference).strip().lower()
        for reference in references
        if str(reference).strip()
    }

    def candidates(value):
        if pd.isna(value):
            return set()

        if isinstance(value, (pd.Timestamp, np.datetime64)):
            timestamp = pd.Timestamp(value)
            return {
                timestamp.isoformat().lower(),
                timestamp.strftime("%Y-%m-%d").lower(),
                timestamp.strftime("%Y-%m").lower(),
                timestamp.strftime("%Y").lower(),
            }

        if isinstance(value, (int, np.integer)):
            integer = int(value)
            return {str(integer), f"{integer}s"}

        if isinstance(value, (float, np.floating)) and float(value).is_integer():
            integer = int(value)
            return {str(integer), f"{integer}s"}

        return {str(value).strip().lower()}

    mask = df[x_col].map(
        lambda value: bool(candidates(value) & normalized_references)
    )
    return df.loc[mask]


def insert_gap_breaks(df, x_col, y_cols, max_gap):
    """
    Insert NaN separator rows where adjacent chart periods are too far apart.

    The returned dataframe is intended only for line rendering. The original
    observations remain unchanged for tables, metrics, trends, and analysis.
    """
    if df.empty:
        return df.copy()

    plotted = df.sort_values(x_col).reset_index(drop=True)

    if len(plotted) < 2:
        return plotted

    rows = []

    for index, row in plotted.iterrows():
        if index > 0:
            previous_x = plotted.iloc[index - 1][x_col]
            current_x = row[x_col]
            gap = current_x - previous_x

            if gap > max_gap:
                separator = {
                    column: np.nan
                    for column in plotted.columns
                }
                separator[x_col] = previous_x + gap / 2

                for y_col in y_cols:
                    separator[y_col] = np.nan

                rows.append(separator)

        rows.append(row.to_dict())

    return pd.DataFrame(rows, columns=plotted.columns)
