from __future__ import annotations

import random
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from climateview.aqs_config import AQS_POLLUTANTS
from climateview.stations import STATIONS


MAP_METRICS = {
    "Temperature": {"key": "temperature", "color": (231, 111, 81)},
    "Rainfall": {"key": "precipitation", "color": (74, 144, 184)},
    "Fine particles": {"key": "pm25", "color": (91, 146, 121)},
    "Ground-level ozone": {"key": "ozone", "color": (91, 146, 121)},
}
METRIC_KEYS = tuple(config["key"] for config in MAP_METRICS.values())


def _render_styles() -> None:
    st.markdown(
        """
        <style>
            .hero-panel {
                box-sizing: border-box;
                margin-bottom: 1rem;
                padding: 1.5rem;
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-top-width: 4px;
                border-radius: 0.75rem;
            }

            .st-key-show_more_patterns button {
                height: 175px;
                border-top: 4px solid rgba(49, 51, 63, 0.2);
            }

            .st-key-show_more_patterns button p {
                font-size: 1.5rem;
                font-weight: 600;
                line-height: 1.2;
            }

            [class*="st-key-pattern_card_"] button {
                height: 175px;
                padding: 1.25rem;
                align-items: flex-start;
                justify-content: flex-start;
                text-align: left;
            }

            .st-key-show_more_patterns button,
            [class*="st-key-pattern_card_"] button {
                transition: border-color 150ms ease, box-shadow 150ms ease,
                    transform 150ms ease;
            }

            .st-key-show_more_patterns button:hover,
            [class*="st-key-pattern_card_"] button:hover {
                border-color: rgba(49, 51, 63, 0.35);
                box-shadow: 0 4px 12px rgba(49, 51, 63, 0.1);
                transform: translateY(-2px);
            }

            [class*="st-key-pattern_card_"] button p {
                font-size: 1rem;
                font-weight: 400;
                line-height: 1.5;
                text-align: left;
                white-space: normal;
            }

            [class*="st-key-pattern_card_"] button p strong {
                display: block;
                margin-bottom: 1.15rem;
                font-size: 1.5rem;
                font-weight: 600;
                line-height: 1.2;
            }

            [class*="st-key-pattern_card_"][class*="_temperature"] button {
                border-top: 4px solid #e76f51;
            }

            [class*="st-key-pattern_card_"][class*="_precipitation"] button {
                border-top: 4px solid #4a90b8;
            }

            [class*="st-key-pattern_card_"][class*="_air_quality"] button {
                border-top: 4px solid #5b9279;
            }

            @media (max-width: 1200px) {
                div[data-testid="stHorizontalBlock"]:has(.map-legend) {
                    flex-wrap: wrap;
                }

                div[data-testid="stHorizontalBlock"]:has(.map-legend)
                > div[data-testid="stColumn"] {
                    flex: 1 1 100%;
                    width: 100%;
                }

                .map-legend {
                    text-align: left !important;
                    white-space: nowrap;
                }

                .st-key-show_more_patterns button,
                [class*="st-key-pattern_card_"] button {
                    height: 220px;
                }
            }

            @media (max-width: 800px) {
                .st-key-show_more_patterns button,
                [class*="st-key-pattern_card_"] button {
                    height: auto;
                    min-height: 150px;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _build_station_dataframe(
    location_summaries: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows = []
    for station_key, station in STATIONS.items():
        location = location_summaries.get(station_key, {})
        metrics = location.get("map_metrics", {})
        row = {
            "station_key": station_key,
            "name": station["name"],
            "lat": station["latitude"],
            "lon": station["longitude"],
            "summary": location.get(
                "summary",
                "Explore long-term climate and air-quality patterns.",
            ),
            "tooltip_transform": (
                "translate(-100%, -80%)"
                if station["longitude"] > -90
                else "translate(0, -80%)"
            ),
        }
        row.update(
            {
                f"{metric}_change": metrics.get(metric, {}).get("change")
                for metric in METRIC_KEYS
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _style_map_stations(
    stations: pd.DataFrame,
    metric_key: str,
) -> pd.DataFrame:
    styled = stations.copy()
    change_column = f"{metric_key}_change"
    magnitudes = styled[change_column].abs().dropna()
    ranks = magnitudes.rank(method="average", pct=True)
    styled["marker_radius"] = ranks.apply(
        lambda rank: 6 if rank <= 1 / 3 else 8 if rank <= 2 / 3 else 10
    ).reindex(styled.index, fill_value=6)
    styled["direction_arrow"] = styled[change_column].apply(
        lambda value: (
            "↑"
            if pd.notna(value) and value > 0
            else "↓"
            if pd.notna(value) and value < 0
            else ""
        )
    )
    styled["arrow_offset"] = styled["marker_radius"].apply(lambda r: [r + 4, 0])
    styled["arrow_size"] = styled["marker_radius"] * 2
    return styled


def _choose_featured_patterns(
    patterns: list[dict[str, Any]],
    count: int = 3,
) -> list[dict[str, Any]]:
    shuffled = list(patterns)
    random.SystemRandom().shuffle(shuffled)
    selected = []
    used_categories = set()
    used_stations = set()

    for pattern in shuffled:
        if (
            pattern.get("category") in used_categories
            or pattern.get("station_key") in used_stations
        ):
            continue
        selected.append(pattern)
        used_categories.add(pattern.get("category"))
        used_stations.add(pattern.get("station_key"))
        if len(selected) == count:
            return selected

    for pattern in shuffled:
        if pattern in selected or pattern.get("station_key") in used_stations:
            continue
        selected.append(pattern)
        used_stations.add(pattern.get("station_key"))
        if len(selected) == count:
            break
    return selected


def _open_location(
    station_key: str,
    *,
    tab: str = "Temperature",
    pollutant: str | None = None,
    season: str | None = None,
) -> None:
    st.session_state.selected_station = station_key
    st.session_state.climate_data_tabs = tab
    if pollutant in AQS_POLLUTANTS:
        st.session_state.air_quality_pollutant = AQS_POLLUTANTS[pollutant][
            "label"
        ]
    if tab == "Temperature":
        st.session_state.temperature_season = (
            season.title() if season else "All year"
        )
        st.session_state.temperature_aggregation = "Year"
    st.session_state.station_navigation_in_progress = True
    st.query_params["location"] = station_key
    st.rerun()


def _render_map(stations: pd.DataFrame) -> None:
    control_column, legend_column = st.columns(
        [3, 2], vertical_alignment="center"
    )
    with control_column:
        metric_label = st.segmented_control(
            "Map view",
            options=list(MAP_METRICS),
            default="Temperature",
            key="map_metric",
            label_visibility="collapsed",
        ) or "Temperature"

    metric = MAP_METRICS[metric_label]
    map_stations = _style_map_stations(stations, metric["key"])
    marker_color = [*metric["color"], 220]

    with legend_column:
        color = ",".join(map(str, metric["color"]))
        st.markdown(
            "<div class='map-legend' style='text-align:right; color:#666; "
            "font-size:0.9rem;'>"
            f"<span style='color:rgb({color});'>●</span> "
            "Larger circles show greater change · "
            "<span style='font-size:1.25em; font-weight:600;'>↑↓</span> "
            "Arrows show increase or decrease"
            "</div>",
            unsafe_allow_html=True,
        )

    marker_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_stations,
        get_position="[lon, lat]",
        get_fill_color=marker_color,
        get_line_color="[255, 255, 255, 230]",
        get_radius="marker_radius",
        radius_units="'pixels'",
        radius_min_pixels=6,
        radius_max_pixels=11,
        line_width_min_pixels=2,
        stroked=True,
        filled=True,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 190, 90, 255],
        id="weather-stations",
    )
    direction_layer = pdk.Layer(
        "TextLayer",
        data=map_stations,
        get_position="[lon, lat]",
        get_text="direction_arrow",
        character_set="'auto'",
        get_color=marker_color,
        get_size="arrow_size",
        size_units="'pixels'",
        get_pixel_offset="arrow_offset",
        get_text_anchor="'start'",
        get_alignment_baseline="'center'",
        billboard=True,
        pickable=False,
        id="change-directions",
    )
    map_deck = st.pydeck_chart(
        pdk.Deck(
            layers=[marker_layer, direction_layer],
            initial_view_state=pdk.ViewState(
                latitude=39.8283,
                longitude=-98.5795,
                zoom=3.0,
                pitch=0,
            ),
            map_provider="carto",
            map_style="road",
            tooltip={
                "html": (
                    "<div style='width:400px; box-sizing:border-box; "
                    "background:white; color:#222; font-size:18px; "
                    "line-height:1.4; padding:12px; white-space:normal; "
                    "border:1px solid rgba(49,51,63,0.2); "
                    "border-radius:0.75rem; "
                    "transform:{tooltip_transform};'>"
                    "<b>{name}</b><br/>"
                    "<span style='color:#666;'>{summary}</span><br/>"
                    "<span style='color:#999;'>Click to open</span>"
                    "</div>"
                ),
                "style": {"backgroundColor": "transparent", "padding": "0"},
            },
        ),
        on_select="rerun",
        selection_mode="single-object",
        width="stretch",
        height=425,
    )
    selected = (
        map_deck.get("selection", {}).get("indices", {}).get("weather-stations", [])
        if map_deck else []
    )
    if selected:
        _open_location(map_stations.iloc[selected[0]]["station_key"])


def _render_patterns(patterns: list[dict[str, Any]]) -> None:
    if not patterns:
        return
    featured_pool = [p for p in patterns if p.get("featured")]
    featured_pool = featured_pool or patterns
    patterns_by_id = {p["id"]: p for p in featured_pool if p.get("id")}
    featured_ids = st.session_state.get("featured_pattern_ids", ())
    featured = [
        patterns_by_id[pattern_id]
        for pattern_id in featured_ids
        if pattern_id in patterns_by_id
    ]
    count = min(3, len(featured_pool))
    if len(featured) != count:
        featured = _choose_featured_patterns(featured_pool, count)
        st.session_state.featured_pattern_ids = tuple(p["id"] for p in featured)

    columns = st.columns(len(featured) + 1)
    for index, (column, pattern) in enumerate(zip(columns, featured)):
        with column:
            tab = pattern.get("tab", "Temperature")
            color_key = tab.lower().replace(" ", "_")
            if st.button(
                f"**{pattern['title']}**\n\n{pattern['summary']}",
                key=f"pattern_card_{index}_{color_key}",
                width="stretch",
            ):
                _open_location(
                    pattern["station_key"],
                    tab=tab,
                    pollutant=pattern.get("pollutant"),
                    season=pattern.get("season"),
                )

    with columns[-1]:
        if st.button(
            "Show more patterns",
            key="show_more_patterns",
            width="stretch",
        ):
            current_ids = {pattern["id"] for pattern in featured}
            remaining = [p for p in featured_pool if p["id"] not in current_ids]
            next_patterns = _choose_featured_patterns(remaining or featured_pool, count)
            st.session_state.featured_pattern_ids = tuple(
                p["id"] for p in next_patterns
            )
            st.rerun()


def render_landing_page(
    location_summaries: dict[str, dict[str, Any]],
    explorable_patterns: list[dict[str, Any]],
) -> None:
    _render_styles()
    stations = _build_station_dataframe(location_summaries)
    st.markdown('<div style="height: 1.5rem;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-panel">'
        '<h1>How has your climate changed?</h1>'
        '<p style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0;">'
        "See how temperatures, rainfall, and air quality have changed across "
        f"decades in {len(stations)} U.S. locations.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    _render_map(stations)
    _render_patterns(explorable_patterns)
    st.caption("Data Sources: NOAA and U.S. EPA")
