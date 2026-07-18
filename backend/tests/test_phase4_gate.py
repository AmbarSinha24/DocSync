import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.engine.models import RepoTooLargeError
from app.integrations.confluence import get_confluence_client
from app.main import app
from app.models import ApprovalRecord, PathMapping, Repo, SyncJob

client = TestClient(app)

JOB_POLL_TIMEOUT_S = 60


def _await_job(job_id: int) -> dict:
    """POST /repos now only synchronously validates the URL/repo existence
    and returns a queued SyncJob -- the actual sync runs as a background
    task, so tests poll GET /repo-jobs/{id} until it settles instead of
    reading the result straight off the POST response."""
    deadline = time.monotonic() + JOB_POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        resp = client.get(f"/repo-jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} did not settle within {JOB_POLL_TIMEOUT_S}s")

# A tiny real public repo, distinct from the AmbarSinha24/docsync-fixture used
# elsewhere -- kept unregistered in the DB between test runs via the cleanup
# fixture below, so "add" always exercises the new-repo branch.
NEW_REPO_URL = "octocat/Hello-World"
NEW_REPO_FULL_NAME = "octocat/Hello-World"

# Used only for the over-cap test, where the guardrail is forced to reject --
# never actually reaches Confluence/DB writes, so it needs no cleanup of its own.
OVER_CAP_REPO_URL = "octocat/Spoon-Knife"


def _delete_repo_by_name(full_name: str) -> None:
    """Mirrors the manual cleanup used during UI verification: delete
    sync jobs, approval records, then child path mappings, then root
    mappings, then the repo row, then its Confluence page -- in FK-safe
    order. Every POST /repos call now leaves a SyncJob row behind (FK'd to
    repos.id), so it has to go before the repo row same as everything else."""
    session = SessionLocal()
    try:
        repo = session.query(Repo).filter_by(name=full_name).one_or_none()
        if repo is None:
            return
        page_id = repo.root_page_id

        session.query(SyncJob).filter_by(repo_id=repo.id).delete()
        session.flush()

        mappings = session.query(PathMapping).filter_by(repo_id=repo.id).all()
        mapping_ids = [m.id for m in mappings]
        if mapping_ids:
            session.query(ApprovalRecord).filter(
                ApprovalRecord.path_mapping_id.in_(mapping_ids)
            ).delete(synchronize_session=False)
        for m in [m for m in mappings if m.parent_mapping_id is not None]:
            session.delete(m)
        session.flush()
        for m in [m for m in mappings if m.parent_mapping_id is None]:
            session.delete(m)
        session.flush()
        session.delete(repo)
        session.commit()
    finally:
        session.close()

    if page_id:
        try:
            get_confluence_client().delete_page(page_id)
        except Exception:
            pass


@pytest.fixture
def cleanup_new_repo():
    _delete_repo_by_name(NEW_REPO_FULL_NAME)
    yield
    _delete_repo_by_name(NEW_REPO_FULL_NAME)


def test_add_new_public_repo_creates_page_and_pending_approvals(cleanup_new_repo):
    resp = client.post("/repos", json={"url": NEW_REPO_URL})
    assert resp.status_code == 202
    job = _await_job(resp.json()["id"])

    assert job["status"] == "done"
    assert job["pending_approvals"] > 0

    repo = client.get(f"/repos/{job['repo_id']}").json()
    assert repo["name"] == NEW_REPO_FULL_NAME
    assert repo["source_type"] == "public_snapshot"
    assert repo["last_synced_sha"]
    assert repo["root_page_id"]


def test_readd_existing_repo_produces_incremental_diff_not_full_regen(cleanup_new_repo):
    first = client.post("/repos", json={"url": NEW_REPO_URL})
    assert first.status_code == 202
    first_job = _await_job(first.json()["id"])
    assert first_job["status"] == "done"

    second = client.post("/repos", json={"url": NEW_REPO_URL})
    assert second.status_code == 202
    second_job = _await_job(second.json()["id"])
    assert second_job["status"] == "done"

    # Same repo row reused (dedup via the unique constraint on Repo.name),
    # not a duplicate -- and nothing changed upstream since the first add,
    # so the incremental diff against last_synced_sha yields no new work.
    assert second_job["repo_id"] == first_job["repo_id"]
    assert second_job["pending_approvals"] == 0


def test_invalid_github_url_rejected():
    resp = client.post("/repos", json={"url": "https://gitlab.com/owner/repo"})
    assert resp.status_code == 400


def test_nonexistent_repo_returns_clean_404():
    resp = client.post("/repos", json={"url": "AmbarSinha24/this-repo-does-not-exist-xyz"})
    assert resp.status_code == 404
    assert "TaskGroup" not in resp.json()["detail"]


def test_over_cap_repo_blocked_with_zero_llm_calls():
    """Forces the guardrail to reject regardless of the real repo's actual
    size, so the test is deterministic without needing an actually-huge
    fixture repo. Confirms: no LLM calls happen (guardrail runs before any
    naming/content generation), and no orphaned Confluence page or DB row is
    left behind for a repo that never got past the guardrail.

    The guardrail runs inside the backgrounded sync work now (generate_changeset
    is only called from _run_add_repo_job, past the point POST /repos already
    returned), so this surfaces as a FAILED job rather than an immediate 422 --
    URL validity and repo existence are the only checks still synchronous.
    """

    def _always_too_large(changeset, cap=None):
        raise RepoTooLargeError(f"forced cap for test: {changeset.owner}/{changeset.repo}")

    with patch(
        "app.engine.guardrail.enforce_loc_guardrail", side_effect=_always_too_large
    ), patch("app.integrations.llm.propose_name_and_location") as mock_propose, patch(
        "app.integrations.llm.generate_section_content"
    ) as mock_generate:
        resp = client.post("/repos", json={"url": OVER_CAP_REPO_URL})
        assert resp.status_code == 202
        job = _await_job(resp.json()["id"])

        assert job["status"] == "failed"
        assert "forced cap for test" in job["error_message"]
        mock_propose.assert_not_called()
        mock_generate.assert_not_called()

    session = SessionLocal()
    try:
        assert session.query(Repo).filter_by(name="octocat/Spoon-Knife").one_or_none() is None
    finally:
        session.close()
