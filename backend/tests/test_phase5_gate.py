import pytest

from app.config import settings
from app.db import SessionLocal
from app.engine.orchestrator import run_sync
from app.engine.recovery import RECOVERY_NOTE
from app.integrations.confluence import get_confluence_client
from app.models import (
    ApprovalRecord,
    ApprovalStatus,
    AuditLog,
    ChangeType,
    PathMapping,
    Repo,
    RepoSourceType,
    SyncStatus,
)

# Real fixture repo -- this exercises the real GitHub MCP tree-walk, just
# against an isolated test Repo DB row so it never touches the actual
# AmbarSinha24/docsync-fixture Repo row used elsewhere.
FIXTURE_OWNER = "AmbarSinha24"
FIXTURE_REPO = "docsync-fixture"
TARGET_SHA = "17636e4648d1499b37977718ee89d4aa36ad4364"
UNREACHABLE_BASELINE_SHA = "0" * 40  # guaranteed absent from the fixture's real history

TEST_REPO_NAME = "test/phase5-force-push-recovery"
STALE_PARENT_PATH = "this-folder-was-deleted"
STALE_SECTION_PATH = "this-folder-was-deleted/old-module"
PENDING_SECTION_PATH = "this-folder-was-deleted/never-approved"


@pytest.fixture
def recovery_repo():
    """A real, auto-committing session (run_sync commits internally, same
    reason test_phase2_gate.py's committing_db fixture exists). Seeds an
    already-synced parent/section pair whose path is guaranteed absent from
    the real fixture repo's current tree (deletion-detection should catch
    it), plus a second, never-synced (still PENDING) section under the same
    parent (deletion-detection should leave it alone -- nothing live exists
    in Confluence for it to delete). Cleans up all rows + any Confluence
    pages created during the test."""
    session = SessionLocal()
    repo = Repo(name=TEST_REPO_NAME, source_type=RepoSourceType.GITHUB_APP)
    session.add(repo)
    session.flush()

    # A real Confluence page is needed here (not a fake page_id) -- DELETE
    # classification fetches the section's live current content to show a
    # reviewer what's being removed, which means a real page_id to fetch.
    client = get_confluence_client()
    root = client.get_page(settings.confluence_root_page_id)
    confluence_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 force-push recovery",
        html_body="<p>throwaway page for test_phase5_gate.py</p>",
    )

    parent = PathMapping(
        repo_id=repo.id,
        path=STALE_PARENT_PATH,
        title="This Folder Was Deleted",
        page_id=confluence_page["id"],
        sync_status=SyncStatus.SYNCED,
    )
    session.add(parent)
    session.flush()

    session.add_all(
        [
            PathMapping(
                repo_id=repo.id,
                path=STALE_SECTION_PATH,
                title="Old Module",
                parent_mapping_id=parent.id,
                section_anchor="sec-test-stale",
                sync_status=SyncStatus.SYNCED,
            ),
            PathMapping(
                repo_id=repo.id,
                path=PENDING_SECTION_PATH,
                title="Never Approved",
                parent_mapping_id=parent.id,
                section_anchor="sec-test-pending",
                sync_status=SyncStatus.PENDING,
            ),
        ]
    )
    session.commit()

    yield session, repo

    session.rollback()  # discard anything left uncommitted if the test body raised

    page_ids = {
        m.page_id
        for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()
        if m.page_id
    }
    mapping_ids = [m.id for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()]
    if mapping_ids:
        approval_ids = [
            a.id
            for a in session.query(ApprovalRecord).filter(
                ApprovalRecord.path_mapping_id.in_(mapping_ids)
            ).all()
        ]
        # AuditLog rows (written by write_approval on every approve/write) must
        # go first -- their FK to approval_records blocks deleting those rows
        # otherwise.
        if approval_ids:
            session.query(AuditLog).filter(
                AuditLog.approval_record_id.in_(approval_ids)
            ).delete(synchronize_session=False)
        session.query(ApprovalRecord).filter(
            ApprovalRecord.path_mapping_id.in_(mapping_ids)
        ).delete(synchronize_session=False)
    session.query(PathMapping).filter(
        PathMapping.repo_id == repo.id, PathMapping.parent_mapping_id.isnot(None)
    ).delete(synchronize_session=False)
    session.query(PathMapping).filter(
        PathMapping.repo_id == repo.id, PathMapping.parent_mapping_id.is_(None)
    ).delete(synchronize_session=False)
    session.query(Repo).filter_by(id=repo.id).delete()
    session.commit()
    session.close()

    client = get_confluence_client()
    for page_id in page_ids:
        try:
            client.delete_page(page_id)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_unreachable_baseline_falls_back_and_reconciles_correctly(recovery_repo):
    session, repo = recovery_repo

    changeset, records = await run_sync(
        session, FIXTURE_OWNER, FIXTURE_REPO, repo, TARGET_SHA, UNREACHABLE_BASELINE_SHA
    )

    # The fallback re-walk ran (not the unreachable baseline) and tagged every
    # record with a recovery note via commit_messages -> pr_context.
    assert changeset.baseline_sha is None
    assert changeset.commit_messages == [RECOVERY_NOTE]

    session.refresh(repo)
    assert repo.last_synced_sha == TARGET_SHA  # the fallback still advances the baseline

    stale_mapping = (
        session.query(PathMapping).filter_by(repo_id=repo.id, path=STALE_SECTION_PATH).one()
    )
    stale_parent_mapping = (
        session.query(PathMapping).filter_by(repo_id=repo.id, path=STALE_PARENT_PATH).one()
    )
    pending_mapping = (
        session.query(PathMapping).filter_by(repo_id=repo.id, path=PENDING_SECTION_PATH).one()
    )

    # The synthetic removal for the stale section is the *only* change in its
    # batch this sync, so the whole stale batch page also classifies DELETE
    # (see _ensure_batch_page) -- and build_approval_records suppresses the
    # now-redundant section-level DELETE for the one section inside it, since
    # deleting the batch page already covers it. One clean proposal instead
    # of two overlapping ones -- and, as a bonus, the previously-orphaned
    # batch page itself now actually gets cleaned up too.
    batch_delete_record = next(
        (r for r in records if r.path_mapping_id == stale_parent_mapping.id), None
    )
    assert batch_delete_record is not None
    assert batch_delete_record.change_type == ChangeType.DELETE
    assert batch_delete_record.status == ApprovalStatus.PENDING
    assert batch_delete_record.pr_context == f"- {RECOVERY_NOTE}"  # _format_pr_context bullets each message

    assert all(r.path_mapping_id != stale_mapping.id for r in records)  # suppressed, covered by the batch delete

    # Never-synced mapping has nothing live in Confluence to delete -- left alone.
    assert all(r.path_mapping_id != pending_mapping.id for r in records)
