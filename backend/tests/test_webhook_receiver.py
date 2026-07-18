import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Repo, RepoSourceType

client = TestClient(app)

ONBOARDED_OWNER = "AmbarSinha24"
ONBOARDED_REPO = "docsync-fixture"
ONBOARDED_NAME = f"{ONBOARDED_OWNER}/{ONBOARDED_REPO}"


def _sign(body: bytes) -> str:
    digest = hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _push_payload(ref="refs/heads/main", owner=ONBOARDED_OWNER, repo=ONBOARDED_REPO, after="abc123"):
    return {
        "ref": ref,
        "before": "0000000000000000000000000000000000000000",
        "after": after,
        "repository": {"name": repo, "owner": {"login": owner}},
    }


@pytest.fixture
def onboarded_repo():
    """The webhook now requires a repo to already be onboarded (a Repo row
    to exist) before it'll dispatch anything -- these fixtures give the
    branch-comparison tests a real onboarded repo to check against, mirroring
    what the Add-Repo UI would have created."""
    session = SessionLocal()
    repo = Repo(
        name=ONBOARDED_NAME,
        source_type=RepoSourceType.PUBLIC_SNAPSHOT,
        default_branch="main",
    )
    session.add(repo)
    session.commit()

    yield repo

    session.rollback()
    session.query(Repo).filter_by(id=repo.id).delete()
    session.commit()
    session.close()


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


def test_push_for_unonboarded_repo_cleanly_ignored():
    body = json.dumps(_push_payload(owner="nobody", repo="never-added")).encode()
    with patch("app.routers.webhooks.process_push", new_callable=AsyncMock) as mock_process:
        resp = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": _sign(body)},
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored", "reason": "repo not onboarded"}
    mock_process.assert_not_called()


def test_push_to_non_main_branch_ignored(onboarded_repo):
    body = json.dumps(_push_payload(ref="refs/heads/feature-x")).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_valid_push_to_main_accepted_and_dispatched(onboarded_repo):
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
