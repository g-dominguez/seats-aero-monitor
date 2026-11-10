import email
import json
import smtplib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import seats_aero_monitor as monitor

FIXTURE = Path(__file__).parent / "fixtures" / "lhr_lax_match.json"


def test_query_route_returns_only_the_qualifying_flight(monkeypatch):
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(monitor.requests, "get", MagicMock(return_value=fake_response))

    lhr_route = monitor.SEARCH_QUERIES[1]
    matches = monitor.query_route(lhr_route, {})

    assert len(matches) == 1
    assert matches[0]["route"] == "LHR → LAX"
    assert matches[0]["points"] == 58000
    assert matches[0]["seats"] == 9
    assert matches[0]["departure_time"] == "04:20 PM"


def set_up_match_and_fake_email(monkeypatch):
    """Fake a search with one match and a working mail server. Returns the fake mail server."""
    # main() searches both routes, so only LHR gets the fixture and NCE gets no results
    def fake_get(url, headers, params, timeout):
        response = MagicMock(status_code=200)
        if params["origin_airport"] == "LHR":
            response.json.return_value = json.loads(FIXTURE.read_text())
        else:
            response.json.return_value = {"data": []}
        return response

    monkeypatch.setattr(monitor.requests, "get", fake_get)

    # Everything in the email code runs for real except the connection to Gmail
    fake_smtp = MagicMock()
    monkeypatch.setattr(monitor.smtplib, "SMTP", fake_smtp)

    # These settings are read when the script is imported, so set them on the module
    monkeypatch.setattr(monitor, "SEATS_AERO_API_KEY", "fake-key")
    monkeypatch.setattr(monitor, "SMTP_USER", "sender@example.com")
    monkeypatch.setattr(monitor, "SMTP_PASSWORD", "fake-password")
    monkeypatch.setattr(monitor, "NOTIFICATION_EMAIL", "me@example.com")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("SEND_TEST_EMAIL", raising=False)
    return fake_smtp


def test_match_sends_email_alert(monkeypatch):
    fake_smtp = set_up_match_and_fake_email(monkeypatch)

    monitor.main()

    server = fake_smtp.return_value
    server.sendmail.assert_called_once()
    sender, recipient, raw_message = server.sendmail.call_args.args
    assert recipient == "me@example.com"

    html_part = email.message_from_string(raw_message).get_payload(0)
    body = html_part.get_payload(decode=True).decode()
    assert "LHR → LAX" in body
    assert "58,000 pts" in body
    assert "04:20 PM" in body
    assert "55,000" not in body
    assert "None" not in body


def test_failed_email_fails_the_run(monkeypatch):
    fake_smtp = set_up_match_and_fake_email(monkeypatch)
    fake_smtp.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    with pytest.raises(SystemExit) as exit_info:
        monitor.main()

    assert exit_info.value.code == 1


def test_missing_email_settings_fail_the_run(monkeypatch):
    set_up_match_and_fake_email(monkeypatch)
    monkeypatch.setattr(monitor, "SMTP_PASSWORD", "")

    with pytest.raises(SystemExit) as exit_info:
        monitor.main()

    assert exit_info.value.code == 1


def test_no_match_does_not_need_email(monkeypatch):
    fake_smtp = set_up_match_and_fake_email(monkeypatch)
    monkeypatch.setattr(monitor, "SMTP_PASSWORD", "")
    empty_response = MagicMock(status_code=200)
    empty_response.json.return_value = {"data": []}
    monkeypatch.setattr(monitor.requests, "get", MagicMock(return_value=empty_response))

    monitor.main()

    fake_smtp.assert_not_called()
