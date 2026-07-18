import asyncio
from unittest.mock import patch

import pytest

from app.db import SessionLocal
from app.engine.models import Changeset
from app.engine.orchestrator import process_push
from app.models import Repo, RepoSourceType

# A fake, isolated owner/repo -- this test never hits real GitHub/LLM/Confluence
# (generate_changeset is mocked below), so there's no need for real coordinates.
TEST_OWNER = "test-owner"
TEST_REPO = "phase5-concurrency-check"
TEST_REPO_NAME = f"{TEST_OWNER}/{TEST_REPO}"


@pytest.fixture
def concurrency_repo():
    session = SessionLocal()
    repo = Repo(
        name=TEST_REPO_NAME, source_type=RepoSourceType.GITHUB_APP, last_synced_sha="sha-0"
    )
    session.add(repo)
    session.commit()

    yield session, repo

    session.rollback()
    session.query(Repo).filter_by(id=repo.id).delete()
    session.commit()
    session.close()


@pytest.mark.asyncio
async def test_concurrent_pushes_for_the_same_repo_serialize_instead_of_racing(concurrency_repo):
    session, repo = concurrency_repo
    call_log: list[dict] = []

    async def fake_generate_changeset(owner, repo_name, target_sha, baseline_sha):
        call_log.append({"target_sha": target_sha, "baseline_sha": baseline_sha})
        # A deliberately wide window: without the per-repo lock, this gives the
        # second concurrent call plenty of time to read the same (still-stale)
        # last_synced_sha before the first call has written its result back.
        await asyncio.sleep(0.3)
        return Changeset(
            owner=owner,
            repo=repo_name,
            target_sha=target_sha,
            baseline_sha=baseline_sha,
            changes=[],
            commit_messages=[],
        )

    with patch(
        "app.engine.orchestrator.generate_changeset", side_effect=fake_generate_changeset
    ):
        await asyncio.gather(
            process_push(TEST_OWNER, TEST_REPO, "sha-A"),
            process_push(TEST_OWNER, TEST_REPO, "sha-B"),
        )

    assert len(call_log) == 2

    first, second = call_log
    # Whichever push actually ran first, the second call must have seen the
    # first call's already-committed target_sha as ITS baseline -- not the
    # original "sha-0" both would have read from if they'd raced.
    assert first["baseline_sha"] == "sha-0"
    assert second["baseline_sha"] == first["target_sha"]

    session.refresh(repo)
    assert repo.last_synced_sha == second["target_sha"]
