import html
from collections.abc import Callable, Hashable

import streamlit as st

from climateview.ai import (
    SummaryGenerationError,
    answer_analysis_question,
    summarize_analysis,
)


_AI_INSIGHTS_CSS = """
<style>
.ai-insights-response {
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

.ai-insights-response::-webkit-scrollbar {
    width: 8px;
    display: block;
}

.ai-insights-response::-webkit-scrollbar-track {
    background: rgba(128, 128, 128, 0.12);
    border-radius: 4px;
}

.ai-insights-response::-webkit-scrollbar-thumb {
    background: rgba(128, 128, 128, 0.55);
    border-radius: 4px;
}
</style>
"""


def _render_response(placeholder, response_text: str) -> None:
    """Render four visible text lines with scrolling for longer responses."""
    escaped_text = html.escape(response_text).replace("\n", "<br>")

    placeholder.markdown(
        f'<div class="ai-insights-response">{escaped_text}</div>',
        unsafe_allow_html=True,
    )


def render_ai_insights(
    *,
    analysis,
    state_prefix: str,
    signature: Hashable,
    render_below: Callable[[tuple[str, ...], tuple[str, ...]], None],
    question_label: str,
    question_placeholder: str,
    summary_spinner_text: str,
    answer_spinner_text: str = "Answering your question...",
) -> None:
    """
    Render the shared AI Insights interface and the content beneath it.

    `analysis` must already reflect the page's currently selected metric,
    station, aggregation, and time range. `signature` should contain every
    selection that changes that analysis.

    `render_below` is called before any AI request, allowing the chart to
    render immediately while the summary or answer is being generated.
    """
    st.markdown(_AI_INSIGHTS_CSS, unsafe_allow_html=True)

    signature_key = f"{state_prefix}_ai_signature"
    text_key = f"{state_prefix}_ai_text"
    mode_key = f"{state_prefix}_ai_mode"
    question_key = f"{state_prefix}_ai_question"
    references_key = f"{state_prefix}_ai_referenced_periods"
    series_key = f"{state_prefix}_ai_referenced_series"

    if st.session_state.get(signature_key) != signature:
        st.session_state[signature_key] = signature
        st.session_state[text_key] = None
        st.session_state[mode_key] = "summary"
        st.session_state[question_key] = ""
        st.session_state[references_key] = ()
        st.session_state[series_key] = ()

    def reset_ai() -> None:
        st.session_state[mode_key] = "summary"
        st.session_state[text_key] = None
        st.session_state[question_key] = ""
        st.session_state[references_key] = ()
        st.session_state[series_key] = ()

    st.subheader("AI Insights")

    with st.container(height=88, border=False):
        insight_placeholder = st.empty()
        insight_text = st.session_state.get(text_key)

        if insight_text:
            _render_response(insight_placeholder, insight_text)

    form_col, reset_col = st.columns(
        [9.1, 0.9],
        vertical_alignment="center",
    )

    with form_col:
        with st.form(
            f"{state_prefix}_ai_form",
            clear_on_submit=False,
            border=False,
        ):
            question_col, ask_col = st.columns(
                [8.0, 1.0],
                vertical_alignment="center",
            )

            with question_col:
                question = st.text_input(
                    question_label,
                    placeholder=question_placeholder,
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
            key=f"{state_prefix}_ai_reset",
            width="stretch",
            on_click=reset_ai,
        )

    # The page supplies its chart or other content here. This is deliberately
    # emitted before any AI request so slow AI generation cannot block it.
    render_below(
        tuple(st.session_state.get(references_key, ())),
        tuple(st.session_state.get(series_key, ())),
    )

    if question_submitted and question.strip():
        try:
            with insight_placeholder.container():
                with st.spinner(answer_spinner_text):
                    answer_response = answer_analysis_question(
                        analysis,
                        question,
                    )

            st.session_state[text_key] = answer_response.text
            st.session_state[mode_key] = "answer"
            st.session_state[references_key] = answer_response.referenced_periods
            st.session_state[series_key] = answer_response.referenced_series
            _render_response(insight_placeholder, answer_response.text)
            st.rerun()

        except SummaryGenerationError:
            insight_placeholder.info(
                "The AI answer is temporarily unavailable."
            )

    elif st.session_state.get(text_key) is None:
        try:
            with insight_placeholder.container():
                with st.spinner(summary_spinner_text):
                    summary_response = summarize_analysis(analysis)

            st.session_state[text_key] = summary_response.text
            st.session_state[mode_key] = "summary"
            # The automatic insight summarizes the chart as a whole. Only a
            # direct answer to a user's question should highlight chart data.
            st.session_state[references_key] = ()
            st.session_state[series_key] = ()
            _render_response(insight_placeholder, summary_response.text)
            st.rerun()

        except SummaryGenerationError:
            insight_placeholder.info(
                "AI Insights are temporarily unavailable. "
                "The chart and statistics are still available."
            )
