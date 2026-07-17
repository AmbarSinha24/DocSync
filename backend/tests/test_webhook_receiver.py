import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def _sign(body: bytes) -> str:
    digest = hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _push_payload(ref="refs/heads/main", owner="AmbarSinha24", repo="docsync-fixture", after="abc123"):
    return {
        "ref": ref,
        "before": "0000000000000000000000000000000000000000",
        "after": after,
        "repository": {"name": repo, "owner": {"login": owner}},
    }


def test_missing_signature_rejected():
    body = json.dumps(_push_payload()).encode()
    resp = client.post("/webhooks/github", content=body, headers={"X-GitHub-Event": "push"})
    assert resp.status_code == 401


def test_wrong_signature_rejected():
    body = json.dumps(_push_payload()).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 401


def test_malformed_json_rejected():
    body = b"not json"
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 400


def test_non_push_event_ignored():
    body = json.dumps(_push_payload()).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_push_to_non_main_branch_ignored():
    body = json.dumps(_push_payload(ref="refs/heads/feature-x")).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_valid_push_to_main_accepted_and_dispatched():
    body = json.dumps(_push_payload()).encode()
    with patch("app.routers.webhooks.process_push", new_callable=AsyncMock) as mock_process:
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["owner"] == "AmbarSinha24"
    assert data["repo"] == "docsync-fixture"
    mock_process.assert_called_once_with("AmbarSinha24", "docsync-fixture", "abc123")
