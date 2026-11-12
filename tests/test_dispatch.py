"""Tests for the AWS scheduler's Lambda handler. No network or AWS calls."""

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scheduler" / "src"))
import dispatch  # noqa: E402

FAKE_TOKEN = "github_pat_fake_for_tests"


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def lambda_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "g-dominguez/seats-aero-monitor")
    monkeypatch.setenv("WORKFLOW_FILE", "monitor.yml")
    monkeypatch.setenv("GIT_REF", "main")
    monkeypatch.setattr(dispatch, "get_token", lambda: FAKE_TOKEN)


def test_handler_starts_monitor_workflow_on_main(lambda_env, monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["request"] = request
        return FakeResponse(200, json.dumps({"workflow_run_id": 123}).encode())

    monkeypatch.setattr(dispatch.urllib.request, "urlopen", fake_urlopen)

    result = dispatch.handler({}, None)

    request = sent["request"]
    assert request.get_method() == "POST"
    assert request.full_url == (
        "https://api.github.com/repos/g-dominguez/seats-aero-monitor"
        "/actions/workflows/monitor.yml/dispatches"
    )
    assert json.loads(request.data) == {"ref": "main"}
    assert request.get_header("Authorization") == f"Bearer {FAKE_TOKEN}"
    assert result == {"status": 200, "workflow_run_id": 123}


def test_handler_accepts_empty_success_response(lambda_env, monkeypatch):
    monkeypatch.setattr(
        dispatch.urllib.request, "urlopen", lambda request, timeout: FakeResponse(204, b"")
    )

    assert dispatch.handler({}, None) == {"status": 204, "workflow_run_id": None}


def test_github_error_fails_the_invocation_without_leaking_token(lambda_env, monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(b'{"message": "Bad credentials"}'),
        )

    monkeypatch.setattr(dispatch.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as error:
        dispatch.handler({}, None)

    assert "401" in str(error.value)
    assert "Bad credentials" in str(error.value)
    assert FAKE_TOKEN not in str(error.value)
