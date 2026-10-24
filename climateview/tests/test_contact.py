import io
import json
from urllib.error import URLError
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from climateview.contact import send_contact, validate_contact


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 'test pass word here')
    monkeypatch.setenv('CONTACT_FROM_EMAIL', 'contact@climatepatterns.app')
    monkeypatch.setenv('CONTACT_TO_EMAIL', 'private@example.com')


@pytest.mark.parametrize('email,message', [('', 'hello'), ('bad', 'hello'),
    ('a@example.com\r\nBcc: x@example.com', 'hello'), ('a@example.com', ''),
    ('a@example.com', 'a' * 1201)])
def test_invalid_input(email, message):
    with pytest.raises(ValueError):
        validate_contact(email, message)


def test_delivery_payload(configured):
    with patch('climateview.contact.urlopen', return_value=io.BytesIO(b'{"id":"sent"}')) as send:
        send_contact('visitor@example.com', '<b>Hello</b>', 'submission-1')
    request = send.call_args.args[0]
    payload = json.loads(request.data)
    assert payload['to'] == ['private@example.com']
    assert payload['from'] == 'contact@climatepatterns.app'
    assert payload['reply_to'] == 'visitor@example.com'
    assert payload['text'].endswith('<b>Hello</b>')
    assert 'html' not in payload
    assert request.get_header('Idempotency-key') == 'submission-1'
    assert send.call_args.kwargs['timeout'] == 15


@pytest.mark.parametrize('failure', [URLError('secret'), OSError('private@example.com')])
def test_provider_error_is_private(configured, failure):
    with patch('climateview.contact.urlopen', side_effect=failure):
        with pytest.raises(RuntimeError, match='Unable to send') as error:
            send_contact('visitor@example.com', 'Hello', 'submission-1')
    assert 'private@example.com' not in str(error.value)
    assert 'secret' not in str(error.value)


def app():
    return AppTest.from_string('''
from climateview import landing_page as page
page._render_map = lambda stations: None
page._render_patterns = lambda patterns: None
page.render_landing_page({}, [])
''').run()


def test_unconfigured_form(monkeypatch):
    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    at = app()
    at.button(key='about_climatepatterns').click().run()
    assert not at.exception
    assert at.button[-1].disabled
    assert not at.info


def test_form_submission_and_cooldown(configured):
    at = AppTest.from_string('from climateview.landing_page import _render_about_dialog; _render_about_dialog()').run()
    at.text_input[0].input('visitor@example.com')
    at.text_area[0].input('A question about climate')
    with patch('climateview.contact.send_contact') as send:
        at.button[-1].click().run()
        assert not at.exception
        assert at.success
        assert send.call_count == 1
        at.button[-1].click().run()
        assert at.warning
        assert send.call_count == 1


def test_form_failure_preserves_message(configured):
    at = AppTest.from_string('from climateview.landing_page import _render_about_dialog; _render_about_dialog()').run()
    at.text_input[0].input('visitor@example.com')
    at.text_area[0].input('Keep this message')
    with patch('climateview.contact.send_contact', side_effect=RuntimeError('failure')):
        at.button[-1].click().run()
    assert not at.exception
    assert at.error
    assert not at.success
    assert at.text_area[0].value == 'Keep this message'
