"""Server-side contact delivery. Credentials and recipient never enter the UI."""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

import streamlit as st

logger = logging.getLogger(__name__)


def contact_configured() -> bool:
    return all(os.environ.get(key, '').strip() for key in (
        'CONTACT_FROM_EMAIL', 'RESEND_API_KEY', 'CONTACT_TO_EMAIL'
    ))


def validate_contact(email: str, message: str) -> None:
    if len(email) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email):
        raise ValueError('Please enter a valid email address.')
    if not message or len(message) > 1200:
        raise ValueError('Please enter a message between 1 and 1,200 characters.')


def send_contact(email: str, message: str, submission_id: str) -> None:
    validate_contact(email, message)
    if not contact_configured():
        raise RuntimeError('Contact form is not configured.')
    payload = {
        'from': os.environ['CONTACT_FROM_EMAIL'].strip(),
        'to': [os.environ['CONTACT_TO_EMAIL'].strip()],
        'reply_to': email,
        'subject': 'ClimatePatterns.app contact message',
        'text': f'Reply email: {email}\n\n{message}',
    }
    request = Request(
        'https://api.resend.com/emails',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f"Bearer {os.environ['RESEND_API_KEY'].strip()}",
            'Content-Type': 'application/json',
            'User-Agent': 'ClimatePatterns/1.0',
            'Idempotency-Key': submission_id,
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
            if not isinstance(result, dict) or not result.get('id'):
                raise ValueError('Missing email ID')
    except (URLError, OSError, ValueError) as exc:
        # Do not expose provider responses, addresses, or credentials.
        logger.warning('Contact delivery failed (%s)', type(exc).__name__)
        raise RuntimeError('Unable to send right now. Please try again shortly.') from None


def render_contact_form() -> None:
    configured = contact_configured()
    with st.form('contact_form'):
        email = st.text_input('Your email address', max_chars=254)
        message = st.text_area('Message', height=180, max_chars=1200)
        submitted = st.form_submit_button('Send', disabled=not configured)
    if not submitted:
        return
    email, message = email.strip(), message.strip()
    try:
        validate_contact(email, message)
    except ValueError as exc:
        st.error(str(exc))
        return
    now = time.monotonic()
    if now - st.session_state.get('contact_last_attempt', float('-inf')) < 60:
        st.warning('Please wait one minute before submitting another message.')
        return
    # Reuse the idempotency key when retrying the same message.
    previous = st.session_state.get('contact_submission')
    if previous is None or previous[:2] != (email, message):
        previous = (email, message, str(uuid.uuid4()))
        st.session_state.contact_submission = previous
    if st.session_state.get('contact_sent_submission') == previous[2]:
        st.success('Thank you! This message has already been submitted.')
        return
    st.session_state.contact_last_attempt = now
    try:
        with st.spinner('Sending your message…'):
            send_contact(email, message, previous[2])
    except RuntimeError:
        st.error('Unable to send right now. Please try again in a minute. Your message is still in the form.')
        return
    st.session_state.contact_sent_submission = previous[2]
    st.success('Thank you! Your message has been submitted.')
