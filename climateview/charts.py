import numpy as np
import plotly.graph_objects as go


def add_trendline(fig, df, x_col, trend_x_col, y_col, name, unit_label):
    trend_data = df[[x_col, trend_x_col, y_col]].dropna()

    if len(trend_data) < 2:
        return None

    x = trend_data[trend_x_col].values
    y = trend_data[y_col].values

    slope_per_year, intercept = np.polyfit(x, y, 1)
    trend_y = slope_per_year * x + intercept

    fig.add_trace(
        go.Scatter(
            x=trend_data[x_col],
            y=trend_y,
            mode="lines",
            name=f"{name} ({slope_per_year:+.3f} {unit_label}/year)",
            line=dict(dash="dash"),
        )
    )

    return slope_per_year