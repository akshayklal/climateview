import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from climateview.ai import (
    SummaryGenerationError,
    answer_analysis_question,
    summarize_analysis,
)
from climateview.statistics import (
    AnalysisContext,
    DataSchema,
    analyze_series,
)

MONTH_NAME_TO_NUMBER = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}



def render_ai_response(placeholder, response_text):
    """Render exactly four visible text lines with a visible scrollbar."""
    escaped_text = html.escape(response_text).replace("\n", "<br>")

    placeholder.markdown(
        f"""
        <div class="precipitation-ai-response">
            {escaped_text}
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_precipitation_aggregation(
    data,
    precipitation_view,
    rain_year_start_month,
):
    if precipitation_view == "Month":
        grouped = (
            data.groupby("month")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_data=("prcp_in", "count"),
                rainy_days=("prcp_in", lambda values: (values > 0).sum()),
            )
            .reset_index()
        )

        grouped["month"] = pd.to_datetime(grouped["month"])
        grouped["year"] = grouped["month"].dt.year
        grouped["trend_year"] = (
            grouped["month"].dt.year
            + (grouped["month"].dt.month - 1) / 12
        )

        x_col = "month"
        x_title = "Month"
        chart_title = "Monthly Precipitation"

    elif precipitation_view == "Calendar Year":
        grouped = (
            data.groupby("year")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_data=("prcp_in", "count"),
                rainy_days=("prcp_in", lambda values: (values > 0).sum()),
            )
            .reset_index()
        )

        grouped = grouped[
            grouped["days_with_data"] >= 300
        ].copy()

        grouped["trend_year"] = grouped["year"]

        x_col = "year"
        x_title = "Year"
        chart_title = "Calendar-Year Precipitation"

    elif precipitation_view == "Rain Year":
        rain_data = data.copy()

        rain_data["rain_year"] = np.where(
            rain_data["month_number"] >= rain_year_start_month,
            rain_data["year"] + 1,
            rain_data["year"],
        )

        grouped = (
            rain_data.groupby("rain_year")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_data=("prcp_in", "count"),
                rainy_days=("prcp_in", lambda values: (values > 0).sum()),
            )
            .reset_index()
        )

        grouped = grouped[
            grouped["days_with_data"] >= 300
        ].copy()

        grouped["year"] = grouped["rain_year"]
        grouped["trend_year"] = grouped["rain_year"]

        x_col = "rain_year"
        x_title = "Rain Year"
        chart_title = "Rain-Year Precipitation"

    else:
        annual = (
            data.groupby("year")
            .agg(
                total_prcp_in=("prcp_in", "sum"),
                days_with_data=("prcp_in", "count"),
                rainy_days=("prcp_in", lambda values: (values > 0).sum()),
            )
            .reset_index()
        )

        annual = annual[
            annual["days_with_data"] >= 300
        ].copy()

        annual["decade"] = (
            annual["year"] // 10
        ) * 10

        grouped = (
            annual.groupby("decade")
            .agg(
                total_prcp_in=("total_prcp_in", "mean"),
                rainy_days=("rainy_days", "mean"),
                years_in_decade=("year", "count"),
            )
            .reset_index()
        )

        grouped["year"] = grouped["decade"]
        grouped["trend_year"] = grouped["decade"]

        x_col = "decade"
        x_title = "Decade"
        chart_title = "Average Annual Precipitation by Decade"

    return grouped, x_col, x_title, chart_title


def calculate_precipitation_trend(data):
    trend_data = data[
        ["trend_year", "total_prcp_in"]
    ].dropna()

    if len(trend_data) < 2:
        return None, None

    slope, intercept = np.polyfit(
        trend_data["trend_year"],
        trend_data["total_prcp_in"],
        1,
    )

    trend_values = (
        slope * data["trend_year"] + intercept
    )

    return float(slope), trend_values


def build_precipitation_figure(
    aggregated_data,
    x_col,
    x_title,
    chart_title,
    station_name,
):
    precipitation_trend, trend_values = (
        calculate_precipitation_trend(
            aggregated_data
        )
    )

    figure = go.Figure()

    figure.add_trace(
        go.Bar(
            x=aggregated_data[x_col],
            y=aggregated_data["total_prcp_in"],
            name="Precipitation",
            hovertemplate=(
                "%{x}<br>"
                "Precipitation: %{y:.2f} in"
                "<extra></extra>"
            ),
        )
    )

    if trend_values is not None:
        figure.add_trace(
            go.Scatter(
                x=aggregated_data[x_col],
                y=trend_values,
                mode="lines",
                name=(
                    "Trend"
                ),
                line={"dash": "dash"},
                hoverinfo="skip",
            )
        )

    figure.update_layout(
        xaxis_title=x_title,
        yaxis_title="Precipitation (inches)",
        height=520,
        margin={
            "l": 40,
            "r": 30,
            "t": 12,
            "b": 100,
        },
        hovermode="x unified",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.20,
            "xanchor": "center",
            "x": 0.5,
        },
        bargap=0.15,
    )

    figure.update_xaxes(
        showgrid=False,
    )

    figure.update_yaxes(
        showgrid=True,
        zeroline=False,
    )

    return figure, precipitation_trend


def calculate_annual_statistics(filtered_data):
    annual_data = (
        filtered_data.groupby("year")
        .agg(
            total_prcp_in=("prcp_in", "sum"),
            days_with_data=("prcp_in", "count"),
            rainy_days=("prcp_in", lambda values: (values > 0).sum()),
        )
        .reset_index()
    )

    annual_data = annual_data[
        annual_data["days_with_data"] >= 300
    ].copy()

    if annual_data.empty:
        return None, None, None, annual_data

    average_annual_precipitation = float(
        annual_data["total_prcp_in"].mean()
    )

    wettest_row = annual_data.loc[
        annual_data["total_prcp_in"].idxmax()
    ]

    driest_row = annual_data.loc[
        annual_data["total_prcp_in"].idxmin()
    ]

    wettest_year = {
        "year": int(wettest_row["year"]),
        "precipitation": float(
            wettest_row["total_prcp_in"]
        ),
    }

    driest_year = {
        "year": int(driest_row["year"]),
        "precipitation": float(
            driest_row["total_prcp_in"]
        ),
    }

    return (
        average_annual_precipitation,
        wettest_year,
        driest_year,
        annual_data,
    )


def render_precipitation_table(
    aggregated_data,
    precipitation_view,
):
    if precipitation_view == "Month":
        display_data = aggregated_data.rename(
            columns={
                "month": "Month",
                "total_prcp_in": "Total precipitation (in)",
                "rainy_days": "Rainy days",
                "days_with_data": "Days with observations",
            }
        )

        display_data["Month"] = display_data[
            "Month"
        ].dt.strftime("%B %Y")

        display_columns = [
            "Month",
            "Total precipitation (in)",
            "Rainy days",
            "Days with observations",
        ]

    elif precipitation_view == "Calendar Year":
        display_data = aggregated_data.rename(
            columns={
                "year": "Year",
                "total_prcp_in": "Total precipitation (in)",
                "rainy_days": "Rainy days",
                "days_with_data": "Days with observations",
            }
        )

        display_columns = [
            "Year",
            "Total precipitation (in)",
            "Rainy days",
            "Days with observations",
        ]

    elif precipitation_view == "Rain Year":
        display_data = aggregated_data.rename(
            columns={
                "rain_year": "Rain year",
                "total_prcp_in": "Total precipitation (in)",
                "rainy_days": "Rainy days",
                "days_with_data": "Days with observations",
            }
        )

        display_columns = [
            "Rain year",
            "Total precipitation (in)",
            "Rainy days",
            "Days with observations",
        ]

    else:
        display_data = aggregated_data.rename(
            columns={
                "decade": "Decade",
                "total_prcp_in": (
                    "Average annual precipitation (in)"
                ),
                "rainy_days": "Average rainy days",
                "years_in_decade": "Years included",
            }
        )

        display_columns = [
            "Decade",
            "Average annual precipitation (in)",
            "Average rainy days",
            "Years included",
        ]

    display_data = display_data[
        display_columns
    ].copy()

    precipitation_columns = [
        "Total precipitation (in)",
        "Average annual precipitation (in)",
    ]

    for column in precipitation_columns:
        if column in display_data.columns:
            display_data[column] = display_data[
                column
            ].round(2)

    if "Average rainy days" in display_data.columns:
        display_data["Average rainy days"] = display_data[
            "Average rainy days"
        ].round(1)

    st.dataframe(
        display_data,
        width="stretch",
        hide_index=True,
    )


def render_precipitation_tab(data, station_name):
    st.markdown(
        """
        <style>
        .precipitation-ai-response {
            box-sizing: border-box;
            height: 5.4rem;
            line-height: 1.35rem;
            overflow-y: scroll;
            overflow-x: hidden;
            padding: 0 0.35rem 0 0;
            margin: 0;
            scrollbar-gutter: stable;
            scrollbar-width: thin;
            scrollbar-color:
                rgba(128, 128, 128, 0.55)
                rgba(128, 128, 128, 0.12);
        }

        .precipitation-ai-response::-webkit-scrollbar {
            width: 8px;
            display: block;
        }

        .precipitation-ai-response::-webkit-scrollbar-track {
            background: rgba(128, 128, 128, 0.12);
            border-radius: 4px;
        }

        .precipitation-ai-response::-webkit-scrollbar-thumb {
            background: rgba(128, 128, 128, 0.55);
            border-radius: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if data is None or data.empty:
        st.warning(
            "No precipitation data is available for this station."
        )
        return

    required_columns = {
        "year",
        "month",
        "month_number",
        "prcp_in",
    }

    missing_columns = required_columns.difference(
        data.columns
    )

    if missing_columns:
        st.error(
            "Precipitation data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    annual_counts = (
        data.groupby("year")
        .agg(
            days_with_data=("prcp_in", "count"),
        )
        .reset_index()
    )

    complete_years = annual_counts[
        annual_counts["days_with_data"] >= 300
    ]["year"]

    if complete_years.empty:
        min_year = int(data["year"].min())
        max_year = int(data["year"].max())
    else:
        min_year = int(complete_years.min())
        max_year = int(complete_years.max())

    view_col, rain_year_col, range_col = st.columns(
        [2.4, 1.4, 3.2],
        vertical_alignment="bottom",
    )

    with view_col:
        precipitation_view = st.segmented_control(
            "Aggregation",
            options=[
                "Month",
                "Calendar Year",
                "Rain Year",
                "Decade",
            ],
            default="Calendar Year",
            key="precipitation_aggregation",
        )

    if precipitation_view is None:
        precipitation_view = "Calendar Year"

    with rain_year_col:
        rain_year_start_name = st.selectbox(
            "Rain year starts",
            options=list(MONTH_NAME_TO_NUMBER.keys()),
            index=9,
            disabled=precipitation_view != "Rain Year",
            key="rain_year_start_month",
        )

    rain_year_start_month = MONTH_NAME_TO_NUMBER[
        rain_year_start_name
    ]

    with range_col:
        selected_years = st.slider(
            "Period",
            min_value=min_year,
            max_value=max_year,
            value=(min_year, max_year),
            key="precipitation_year_range",
        )

    filtered_data = data[
        data["year"].between(
            selected_years[0],
            selected_years[1],
        )
    ].copy()

    aggregated_data, x_col, x_title, chart_title = (
        build_precipitation_aggregation(
            filtered_data,
            precipitation_view,
            rain_year_start_month,
        )
    )

    if aggregated_data.empty:
        st.info(
            "No sufficiently complete precipitation records "
            "are available for the selected period."
        )
        return

    figure, precipitation_trend = (
        build_precipitation_figure(
            aggregated_data=aggregated_data,
            x_col=x_col,
            x_title=x_title,
            chart_title=chart_title,
            station_name=station_name,
        )
    )

    (
        average_annual_precipitation,
        wettest_year,
        driest_year,
        annual_data,
    ) = calculate_annual_statistics(filtered_data)

    metric1, metric2, metric3, metric4 = st.columns(4)

    metric1.metric(
        "Precipitation trend",
        (
            f"{precipitation_trend:+.3f} in/year"
            if precipitation_trend is not None
            else "Insufficient data"
        ),
    )

    metric2.metric(
        "Annual average",
        (
            f"{average_annual_precipitation:.1f} in"
            if average_annual_precipitation is not None
            else "Insufficient data"
        ),
    )

    metric3.metric(
        "Wettest year",
        (
            str(wettest_year["year"])
            if wettest_year is not None
            else "Insufficient data"
        ),
        (
            f"{wettest_year['precipitation']:.1f} in"
            if wettest_year is not None
            else None
        ),
    )

    metric4.metric(
        "Driest year",
        (
            str(driest_year["year"])
            if driest_year is not None
            else "Insufficient data"
        ),
        (
            f"{driest_year['precipitation']:.1f} in"
            if driest_year is not None
            else None
        ),
    )

    analysis = analyze_series(
        dataframe=aggregated_data,
        context=AnalysisContext(
            location=station_name,
            metric="precipitation",
            unit="inches",
            aggregation=precipitation_view.lower().replace(" ", "_"),
            start_period=selected_years[0],
            end_period=selected_years[1],
        ),
        schema=DataSchema(
            period_column=x_col,
            value_column="total_prcp_in",
        ),
    )

    insight_signature = (
        station_name,
        precipitation_view,
        selected_years[0],
        selected_years[1],
        rain_year_start_month,
    )

    signature_key = "precipitation_ai_signature"
    text_key = "precipitation_ai_text"
    mode_key = "precipitation_ai_mode"
    question_key = "precipitation_ai_question"

    signature_changed = (
        st.session_state.get(signature_key)
        != insight_signature
    )

    if signature_changed:
        st.session_state[signature_key] = insight_signature
        st.session_state[text_key] = None
        st.session_state[mode_key] = "summary"
        st.session_state[question_key] = ""

    def reset_precipitation_ai():
        st.session_state[mode_key] = "summary"
        st.session_state[text_key] = None
        st.session_state[question_key] = ""

    st.subheader("AI Insights")

    # Reserve exactly four visible text lines. Longer responses scroll
    # inside the response viewport without moving the chart.
    with st.container(height=88, border=False):
        insight_placeholder = st.empty()

        insight_text = st.session_state.get(text_key)

        if insight_text:
            render_ai_response(
                insight_placeholder,
                insight_text,
            )

    # Follow-up controls sit below the automatic summary so the page reads
    # naturally: review the insight first, then ask a specific question.
    form_col, reset_col = st.columns(
        [9.1, 0.9],
        vertical_alignment="center",
    )

    with form_col:
        with st.form(
            "precipitation_ai_form",
            clear_on_submit=False,
            border=False,
        ):
            question_col, ask_col = st.columns(
                [8.0, 1.0],
                vertical_alignment="center",
            )

            with question_col:
                question = st.text_input(
                    "Ask a question about the selected precipitation data",
                    placeholder="Ask about trends, anomalies, or specific years...",
                    key=question_key,
                    label_visibility="collapsed",
                )

            with ask_col:
                question_submitted = st.form_submit_button(
                    "Ask",
                    width="stretch",
                )

    with reset_col:
        st.button(
            "Reset",
            key="precipitation_ai_reset",
            width="stretch",
            on_click=reset_precipitation_ai,
        )

    # Render the chart immediately, before waiting for the AI response.
    st.plotly_chart(
        figure,
        width="stretch",
        config={
            "displayModeBar": False,
            "responsive": True,
        },
    )

    # Run AI work only after the chart has been emitted. Both the initial
    # summary and submitted questions use the same AI-area placeholder,
    # keeping the spinner out of the bottom of the page.
    if question_submitted and question.strip():
        try:
            with insight_placeholder.container():
                with st.spinner("Answering your question..."):
                    answer_response = answer_analysis_question(
                        analysis,
                        question,
                    )

            st.session_state[text_key] = answer_response.text
            st.session_state[mode_key] = "answer"

            render_ai_response(
                insight_placeholder,
                answer_response.text,
            )

        except SummaryGenerationError:
            insight_placeholder.info(
                "The AI answer is temporarily unavailable."
            )

    elif st.session_state.get(text_key) is None:
        try:
            with insight_placeholder.container():
                with st.spinner(
                    "Analyzing the selected precipitation data..."
                ):
                    summary_response = summarize_analysis(
                        analysis
                    )

            st.session_state[text_key] = summary_response.text
            st.session_state[mode_key] = "summary"

            render_ai_response(
                insight_placeholder,
                summary_response.text,
            )

        except SummaryGenerationError:
            insight_placeholder.info(
                "AI Insights are temporarily unavailable. "
                "The chart and statistics are still available."
            )

    with st.expander(
        "View underlying precipitation data",
        expanded=False,
    ):
        render_precipitation_table(
            aggregated_data,
            precipitation_view,
        )