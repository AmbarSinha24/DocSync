import pytest

from app.config import settings
from app.db import SessionLocal
from app.engine.approval_builder import build_approval_records
from app.engine.confluence_writer import write_approval
from app.engine.models import Changeset, FileChange
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

TEST_REPO_NAME = "test/phase5-batch-nesting"

# Deliberately unusual folder names, not "backend"/"src" etc. -- the LLM
# proposes a page title from the path, and a generic name here would collide
# with a real page of the same title already living in the same Confluence
# space (this bit a first draft of this file: "backend" collided with the
# real AmbarSinha24/Cabo_Game repo's actual "Backend Overview" page).
PARENT_FOLDER = "nestparenttest"
CHILD_FOLDER = "nestparenttest/childlib"


def _fake_changeset(changes: list[FileChange]) -> Changeset:
    return Changeset(
        owner="test-owner",
        repo="test-repo",
        target_sha="fake-sha-for-batch-nesting-test",
        baseline_sha="fake-baseline-for-batch-nesting-test",
        changes=changes,
    )


def _approve_and_write(session, record: ApprovalRecord, approver: str) -> None:
    record.status = ApprovalStatus.APPROVED
    record.approver = approver
    session.commit()
    write_approval(session, record.id)
    session.commit()


def _cleanup_repo(repo_name: str) -> None:
    session = SessionLocal()
    try:
        repo = session.query(Repo).filter_by(name=repo_name).one_or_none()
        if repo is None:
            return
        mappings = session.query(PathMapping).filter_by(repo_id=repo.id).all()
        page_ids = {m.page_id for m in mappings if m.page_id}
        mapping_ids = [m.id for m in mappings]
        if mapping_ids:
            approval_ids = [
                a.id
                for a in session.query(ApprovalRecord)
                .filter(ApprovalRecord.path_mapping_id.in_(mapping_ids))
                .all()
            ]
            if approval_ids:
                session.query(AuditLog).filter(
                    AuditLog.approval_record_id.in_(approval_ids)
                ).delete(synchronize_session=False)
            session.query(ApprovalRecord).filter(
                ApprovalRecord.path_mapping_id.in_(mapping_ids)
            ).delete(synchronize_session=False)
        # parent_batch_mapping_id and parent_mapping_id both self-reference
        # path_mappings -- null them out first so the FK never blocks delete
        # regardless of which rows get removed in which order.
        session.query(PathMapping).filter_by(repo_id=repo.id).update(
            {"parent_mapping_id": None, "parent_batch_mapping_id": None},
            synchronize_session=False,
        )
        session.flush()
        session.query(PathMapping).filter_by(repo_id=repo.id).delete()
        session.query(Repo).filter_by(id=repo.id).delete()
        session.commit()
    finally:
        session.close()

    if page_ids:
        client = get_confluence_client()
        for page_id in page_ids:
            try:
                client.delete_page(page_id)
            except Exception:
                pass


@pytest.fixture
def nesting_repo():
    _cleanup_repo(TEST_REPO_NAME)
    session = SessionLocal()
    repo = Repo(
        name=TEST_REPO_NAME,
        source_type=RepoSourceType.GITHUB_APP,
        root_page_id=settings.confluence_root_page_id,
    )
    session.add(repo)
    session.commit()

    yield session, repo

    session.rollback()
    session.close()
    _cleanup_repo(TEST_REPO_NAME)


def test_child_only_changeset_with_no_natural_parent_stays_top_level(nesting_repo):
    """A change under the child folder with no direct file ever touched in
    its parent folder, and no prior parent mapping -- the parent was never
    independently real, so the child batch stays top-level. Nothing here
    should invent a folder-overview page that wouldn't otherwise exist."""
    session, repo = nesting_repo
    changeset = _fake_changeset([FileChange(path=f"{CHILD_FOLDER}/db.js", status="added")])

    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    mappings = {m.path: m for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()}
    assert PARENT_FOLDER not in mappings
    assert CHILD_FOLDER in mappings
    assert mappings[CHILD_FOLDER].parent_batch_mapping_id is None

    child_record = next(r for r in records if r.path_mapping_id == mappings[CHILD_FOLDER].id)
    assert child_record.change_type == ChangeType.CREATE


def test_child_batch_links_to_parent_that_exists_from_a_prior_sync(nesting_repo):
    """The parent folder was already synced before the child folder ever
    appeared -- a later sync touching only the child should still link it
    to the pre-existing parent mapping, not leave it top-level."""
    session, repo = nesting_repo
    first_changeset = _fake_changeset([FileChange(path=f"{PARENT_FOLDER}/index.js", status="added")])
    build_approval_records(session, repo.id, first_changeset)
    session.commit()

    parent_mapping = session.query(PathMapping).filter_by(repo_id=repo.id, path=PARENT_FOLDER).one()

    second_changeset = _fake_changeset([FileChange(path=f"{CHILD_FOLDER}/db.js", status="added")])
    records = build_approval_records(session, repo.id, second_changeset)
    session.commit()

    child_mapping = session.query(PathMapping).filter_by(repo_id=repo.id, path=CHILD_FOLDER).one()
    assert child_mapping.parent_batch_mapping_id == parent_mapping.id

    child_record = next(r for r in records if r.path_mapping_id == child_mapping.id)
    assert child_record.change_type == ChangeType.CREATE


def test_child_batch_page_nests_under_parent_when_parent_approved_first(nesting_repo):
    session, repo = nesting_repo
    client = get_confluence_client()
    changeset = _fake_changeset([
        FileChange(path=f"{PARENT_FOLDER}/index.js", status="added"),
        FileChange(path=f"{CHILD_FOLDER}/db.js", status="added"),
    ])
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    mappings = {m.path: m for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()}
    parent_record = next(r for r in records if r.path_mapping_id == mappings[PARENT_FOLDER].id)
    child_record = next(r for r in records if r.path_mapping_id == mappings[CHILD_FOLDER].id)

    _approve_and_write(session, parent_record, "alice")
    _approve_and_write(session, child_record, "alice")

    session.refresh(mappings[PARENT_FOLDER])
    session.refresh(mappings[CHILD_FOLDER])
    child_page = client.get_page(mappings[CHILD_FOLDER].page_id)
    assert child_page["parentId"] == mappings[PARENT_FOLDER].page_id


def test_child_batch_created_before_parent_self_heals_on_next_write(nesting_repo):
    """Reviewer approves the child batch's CREATE before the parent's --
    the child's page lands under repo root for now (no parent page to nest
    under yet), then self-heals to the correct parent once a later write
    to the child batch happens after the parent exists."""
    session, repo = nesting_repo
    client = get_confluence_client()
    changeset = _fake_changeset([
        FileChange(path=f"{PARENT_FOLDER}/index.js", status="added"),
        FileChange(path=f"{CHILD_FOLDER}/db.js", status="added"),
    ])
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    mappings = {m.path: m for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()}
    parent_record = next(r for r in records if r.path_mapping_id == mappings[PARENT_FOLDER].id)
    child_record = next(r for r in records if r.path_mapping_id == mappings[CHILD_FOLDER].id)

    # Child approved+written first -- parent has no page_id yet.
    _approve_and_write(session, child_record, "bob")
    session.refresh(mappings[CHILD_FOLDER])
    child_page_id = mappings[CHILD_FOLDER].page_id
    assert client.get_page(child_page_id)["parentId"] == repo.root_page_id

    # Now the parent gets approved+written.
    _approve_and_write(session, parent_record, "bob")
    session.refresh(mappings[PARENT_FOLDER])

    # A later sync touches the child folder again -- this write's self-heal
    # check should notice the mismatch and move the child page.
    changeset2 = _fake_changeset([FileChange(path=f"{CHILD_FOLDER}/queue.js", status="added")])
    records2 = build_approval_records(session, repo.id, changeset2)
    session.commit()
    child_edit_record = next(r for r in records2 if r.path_mapping_id == mappings[CHILD_FOLDER].id)
    assert child_edit_record.change_type == ChangeType.CONTENT_EDIT
    _approve_and_write(session, child_edit_record, "bob")

    assert client.get_page(child_page_id)["parentId"] == mappings[PARENT_FOLDER].page_id


def test_pre_existing_flat_batches_backfill_link_and_self_heal(nesting_repo):
    """Simulates a repo synced before batch nesting existed: both batch
    pages already created flat, directly under repo root, with no
    parent_batch_mapping_id linkage. A later sync should backfill the link
    and the next write to the child should self-heal its real parent."""
    session, repo = nesting_repo
    client = get_confluence_client()

    root = client.get_page(repo.root_page_id)
    parent_page = client.create_page(
        space_id=root["spaceId"], parent_id=repo.root_page_id,
        title="[test] phase5 nesting legacy parent", html_body="<p>parent overview</p>",
    )
    child_page = client.create_page(
        space_id=root["spaceId"], parent_id=repo.root_page_id,
        title="[test] phase5 nesting legacy child", html_body="<p>child overview</p>",
    )
    parent_mapping = PathMapping(
        repo_id=repo.id, path=PARENT_FOLDER, title="[test] phase5 nesting legacy parent",
        page_id=parent_page["id"], section_anchor="sec-test-nesting-legacy-parent",
        sync_status=SyncStatus.SYNCED,
    )
    child_mapping = PathMapping(
        repo_id=repo.id, path=CHILD_FOLDER, title="[test] phase5 nesting legacy child",
        page_id=child_page["id"], section_anchor="sec-test-nesting-legacy-child",
        sync_status=SyncStatus.SYNCED,
    )
    session.add_all([parent_mapping, child_mapping])
    session.commit()
    assert child_mapping.parent_batch_mapping_id is None  # pre-fix state

    changeset = _fake_changeset([FileChange(path=f"{CHILD_FOLDER}/queue.js", status="added")])
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    session.refresh(child_mapping)
    assert child_mapping.parent_batch_mapping_id == parent_mapping.id

    child_edit_record = next(r for r in records if r.path_mapping_id == child_mapping.id)
    assert child_edit_record.change_type == ChangeType.CONTENT_EDIT
    _approve_and_write(session, child_edit_record, "carol")

    assert client.get_page(child_mapping.page_id)["parentId"] == parent_mapping.page_id
