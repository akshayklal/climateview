import random

import pandas as pd
import pydeck as pdk
import streamlit as st

from climateview.data_loader import load_precipitation_data
from climateview.data_loader import load_temperature_data
from climateview.data_loader import load_location_summaries
from climateview.data_loader import load_explorable_patterns
from climateview.precipitation import render_precipitation_tab
from climateview.temperature import render_temperature_tab
from climateview.air_quality import render_air_quality_tab
from climateview.data_loader import load_air_quality_data
from climateview.aqs_config import AQS_POLLUTANTS
from climateview.stations import STATIONS


MAP_METRICS = {
    "Temperature": {
        "key": "temperature",
        "color": (231, 111, 81),
    },
    "Rainfall": {
        "key": "precipitation",
        "color": (74, 144, 184),
    },
    "Fine particles": {
        "key": "pm25",
        "color": (91, 146, 121),
    },
    "Ground-level ozone": {
        "key": "ozone",
        "color": (91, 146, 121),
    },
}


def _choose_featured_patterns(
    patterns: list[dict],
    count: int = 3,
) -> list[dict]:
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


# Page configuration
st.set_page_config(
    page_title="Climate Patterns",
    page_icon="🌎",
    layout="wide",
)

# Hide stale content only while navigating between the map and station page.
if "station_navigation_in_progress" not in st.session_state:
    st.session_state.station_navigation_in_progress = False

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1.5rem;
        }

        h1 {
            margin-top: 0;
            margin-bottom: 0.25rem;
        }

        [data-testid="stCaptionContainer"] {
            margin-bottom: 0.25rem;
        }

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
    </style>
    """,
    unsafe_allow_html=True,
)

if st.session_state.station_navigation_in_progress:
    st.markdown(
        """
        <style>
            /* Hide the previous page only during map/station navigation. */
            [data-stale="true"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

# Build station dataframe for the map
location_summaries = load_location_summaries()
explorable_patterns = load_explorable_patterns()
df_stations = pd.DataFrame(
    [
        {
            "station_key": station_key,
            "name": station["name"],
            "lat": station["latitude"],
            "lon": station["longitude"],
            "summary": location_summaries.get(station_key, {}).get(
                "summary",
                "Explore long-term climate and air-quality patterns.",
            ),
            **{
                f"{metric}_change": location_summaries.get(
                    station_key,
                    {},
                ).get("map_metrics", {}).get(metric, {}).get("change")
                for metric in ("temperature", "precipitation", "pm25", "ozone")
            },
            "tooltip_transform": (
                "translate(-100%, -80%)"
                if station["longitude"] > -90
                else "translate(0, -80%)"
            ),
        }
        for station_key, station in STATIONS.items()
    ]
)

# Keep the selected location in both the URL and session state. The URL makes
# location pages bookmarkable, shareable, and resilient to browser refreshes.
url_location = st.query_params.get("location")

if url_location in STATIONS:
    st.session_state.selected_station = url_location
else:
    st.session_state.selected_station = None
    if url_location is not None:
        del st.query_params["location"]

# SCREEN 2: Selected station detail page
if st.session_state.selected_station in STATIONS:
    # The transition CSS has already been emitted for this rerun.
    # Disable it for later tab and control reruns.
    st.session_state.station_navigation_in_progress = False

    station_key = st.session_state.selected_station
    station = STATIONS[station_key]

    station_name = station["name"]
    noaa_station_id = station["noaa_station_id"]

    # Compact navigation and station header
    back_col, title_col = st.columns(
        [1, 8],
        vertical_alignment="center",
    )

    with back_col:
        if st.button("← All locations"):
            st.session_state.selected_station = None
            st.session_state.station_navigation_in_progress = True
            if "location" in st.query_params:
                del st.query_params["location"]
            st.rerun()

    with title_col:
        st.markdown(f"## {station_name}")

    temperature_data = load_temperature_data(
        station_id=noaa_station_id
    )

    precipitation_data = load_precipitation_data(
        station_id=noaa_station_id
    )

    aqs_site_id = station.get("aqs_site_id")

    if aqs_site_id:
        pm25_data = load_air_quality_data(
            aqs_site_id=aqs_site_id,
            pollutant="pm25",
        )

        ozone_data = load_air_quality_data(
            aqs_site_id=aqs_site_id,
            pollutant="ozone",
        )
    else:
        pm25_data = {
            "metadata": {},
            "data": pd.DataFrame(),
        }

        ozone_data = {
            "metadata": {},
            "data": pd.DataFrame(),
        }

    # Detail tabs
    temperature_tab, precipitation_tab, air_quality_tab = st.tabs(
        ["Temperature", "Precipitation", "Air Quality"],
        key="climate_data_tabs",
        on_change="rerun",
    )

    if temperature_tab.open:
        with temperature_tab:
            render_temperature_tab(
                temperature_data,
                station_name=station_name,
            )

    elif precipitation_tab.open:
        with precipitation_tab:
            render_precipitation_tab(
                precipitation_data,
                station_name=station_name,
            )

    elif air_quality_tab.open:
        with air_quality_tab:
            render_air_quality_tab(
                pm25_data=pm25_data,
                ozone_data=ozone_data,
                station_name=station_name,
            )

# SCREEN 1: Landing page and station map
else:
    # Hero section
    st.markdown('<div style="height: 1.5rem;"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-panel">'
        '<h1>How has your climate changed?</h1>'
        '<p style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0;">'
        "See how temperatures, rainfall, and air quality have changed across "
        f"decades in {len(df_stations)} U.S. locations.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    control_column, legend_column = st.columns(
        [3, 2],
        vertical_alignment="center",
    )
    with control_column:
        map_metric_label = st.segmented_control(
            "Map view",
            options=list(MAP_METRICS),
            default="Temperature",
            key="map_metric",
            label_visibility="collapsed",
        ) or "Temperature"

    metric_config = MAP_METRICS[map_metric_label]
    metric_key = metric_config["key"]
    metric_column = f"{metric_key}_change"
    map_stations = df_stations.copy()
    magnitudes = map_stations[metric_column].abs().dropna()
    magnitude_ranks = magnitudes.rank(method="average", pct=True)
    map_stations["marker_radius"] = magnitude_ranks.apply(
        lambda rank: 6 if rank <= 1 / 3 else 9 if rank <= 2 / 3 else 12
    ).reindex(map_stations.index, fill_value=6)
    map_stations["marker_color"] = [
        [*metric_config["color"], 220]
        for _ in range(len(map_stations))
    ]
    map_stations["direction_arrow"] = map_stations[metric_column].apply(
        lambda value: "↑" if pd.notna(value) and value > 0 else "↓"
        if pd.notna(value) and value < 0
        else ""
    )
    map_stations["arrow_offset"] = map_stations["marker_radius"].apply(
        lambda radius: [radius + 4, 0]
    )
    map_stations["arrow_size"] = map_stations["marker_radius"] * 2

    with legend_column:
        metric_color = ",".join(map(str, metric_config["color"]))
        st.markdown(
            "<div style='text-align:right; color:#666; font-size:0.9rem;'>"
            f"<span style='color:rgb({metric_color});'>●</span> "
            "Larger circles show greater change · "
            "<span style='font-size:1.25em; font-weight:600;'>↑↓</span> "
            "Arrows show increase or decrease"
            "</div>",
            unsafe_allow_html=True,
        )

    # Station marker layer
    station_layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_stations,
        get_position="[lon, lat]",
        get_fill_color="marker_color",
        get_line_color="[255, 255, 255, 230]",
        get_radius="marker_radius",
        radius_units="'pixels'",
        radius_min_pixels=6,
        radius_max_pixels=13,
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
        get_color="marker_color",
        get_size="arrow_size",
        size_units="'pixels'",
        get_pixel_offset="arrow_offset",
        get_text_anchor="'start'",
        get_alignment_baseline="'center'",
        billboard=True,
        pickable=False,
        id="change-directions",
    )

    # Initial map position
    view_state = pdk.ViewState(
        latitude=39.8283,
        longitude=-98.5795,
        zoom=3.65,
        pitch=0,
    )

    # Render interactive map
    map_deck = st.pydeck_chart(
        pdk.Deck(
            layers=[station_layer, direction_layer],
            initial_view_state=view_state,
            map_provider="carto",
            map_style="road",
            tooltip={
                "html": (
                    "<div style='width:400px; box-sizing:border-box; "
                    "background:white; color:#222; font-size:18px; "
                    "line-height:1.4; padding:12px; white-space:normal; "
                    "border:1px solid rgba(49,51,63,0.2); border-radius:0.75rem; "
                    "transform:{tooltip_transform};'>"
                    "<b>{name}</b><br/>"
                    "<span style='color:#666;'>{summary}</span><br/>"
                    "<span style='color:#999;'>Click to open</span>"
                    "</div>"
                ),
                "style": {
                    "backgroundColor": "transparent",
                    "padding": "0",
                },
            },
        ),
        on_select="rerun",
        selection_mode="single-object",
        width="stretch",
        height=630,
    )

    # Handle map selection
    if (
        map_deck
        and "selection" in map_deck
        and map_deck["selection"]
    ):
        selected_indices = (
            map_deck["selection"]
            .get("indices", {})
            .get("weather-stations", [])
        )

        if selected_indices:
            clicked_index = selected_indices[0]
            clicked_row = df_stations.iloc[clicked_index]

            st.session_state.selected_station = (
                clicked_row["station_key"]
            )
            st.session_state.climate_data_tabs = "Temperature"
            st.session_state.temperature_season = "All year"
            st.session_state.temperature_aggregation = "Year"
            st.session_state.station_navigation_in_progress = True
            st.query_params["location"] = clicked_row["station_key"]

            st.rerun()

    # Featured patterns
    if explorable_patterns:
        featured_pool = [
            pattern
            for pattern in explorable_patterns
            if pattern.get("featured")
        ] or explorable_patterns
        patterns_by_id = {
            pattern["id"]: pattern
            for pattern in featured_pool
            if pattern.get("id")
        }
        featured_ids = st.session_state.get("featured_pattern_ids", ())
        featured_patterns = [
            patterns_by_id[pattern_id]
            for pattern_id in featured_ids
            if pattern_id in patterns_by_id
        ]
        expected_count = min(3, len(featured_pool))
        if len(featured_patterns) != expected_count:
            featured_patterns = _choose_featured_patterns(
                featured_pool,
                expected_count,
            )
            st.session_state.featured_pattern_ids = tuple(
                pattern["id"] for pattern in featured_patterns
            )

        pattern_columns = st.columns(len(featured_patterns) + 1)
        for index, (column, pattern) in enumerate(zip(
            pattern_columns[:len(featured_patterns)],
            featured_patterns,
        )):
            with column:
                pattern_color_key = pattern.get(
                    "tab",
                    "Temperature",
                ).lower().replace(" ", "_")
                if st.button(
                    f"**{pattern['title']}**\n\n{pattern['summary']}",
                    key=f"pattern_card_{index}_{pattern_color_key}",
                    width="stretch",
                ):
                    station_key = pattern["station_key"]
                    st.session_state.selected_station = station_key
                    st.session_state.climate_data_tabs = pattern.get(
                        "tab",
                        "Temperature",
                    )
                    pollutant = pattern.get("pollutant")
                    if pollutant in AQS_POLLUTANTS:
                        st.session_state.air_quality_pollutant = (
                            AQS_POLLUTANTS[pollutant]["label"]
                        )
                    season = pattern.get("season")
                    if pattern.get("tab") == "Temperature":
                        st.session_state.temperature_season = (
                            season.title() if season else "All year"
                        )
                        st.session_state.temperature_aggregation = "Year"
                    st.session_state.station_navigation_in_progress = True
                    st.query_params["location"] = station_key
                    st.rerun()

        with pattern_columns[-1]:
            if st.button(
                "Show more patterns",
                key="show_more_patterns",
                width="stretch",
            ):
                current_ids = {
                    pattern["id"] for pattern in featured_patterns
                }
                remaining_patterns = [
                    pattern
                    for pattern in featured_pool
                    if pattern["id"] not in current_ids
                ]
                next_patterns = _choose_featured_patterns(
                    remaining_patterns or featured_pool,
                    expected_count,
                )
                st.session_state.featured_pattern_ids = tuple(
                    pattern["id"] for pattern in next_patterns
                )
                st.rerun()

    st.caption(
        "Data Sources: NOAA and U.S. EPA"
    )
