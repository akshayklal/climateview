from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from climateview.stations import STATIONS


def test_back_discards_stale_map_selection():
    station = next(iter(STATIONS))
    chart_keys = []

    def chart(*args, **kwargs):
        key = kwargs.get('key')
        chart_keys.append(key)
        # Model the chart retaining a clicked marker until its key changes.
        return {'selection': {'indices': {'weather-stations': [0] if key == 'station_map_0' else []}}}

    with ExitStack() as stack:
        for name in ('temperature', 'precipitation', 'air_quality'):
            stack.enter_context(patch(f'climateview.data_loader.load_{name}_data', return_value={}))
            stack.enter_context(patch(f'climateview.{name}.render_{name}_tab'))
        stack.enter_context(patch('climateview.data_loader.load_location_summaries', return_value={key: {'map_metrics': {'temperature': {'change': 1.0}}} for key in STATIONS}))
        stack.enter_context(patch('climateview.data_loader.load_explorable_patterns', return_value=[]))
        stack.enter_context(patch('streamlit.pydeck_chart', side_effect=chart))
        at = AppTest.from_file(str(Path(__file__).resolve().parents[2] / 'app.py'))
        at.query_params['location'] = station
        at.run()
        assert not at.exception
        next(button for button in at.button if button.label == '← All locations').click().run()
        assert not at.exception
        assert 'location' not in at.query_params
        assert at.session_state.selected_station is None
        assert chart_keys == ['station_map_1']
        assert not at.session_state.station_navigation_in_progress
        assert any('How has your climate changed?' in item.value for item in at.markdown)
        # Further reruns must stay on the map.
        at.run()
        assert not at.exception
        assert at.session_state.selected_station is None
