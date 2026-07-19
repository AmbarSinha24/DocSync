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

TEST_REPO_NAME = "test/phase5-retention"

# Distinctive names -- generic ones like "backend" collide with real page
# titles already living in the same Confluence space (bit a prior test file
# this exact way earlier in the project).
PARENT_FOLDER = "retentiontestparent"
SECTION_PATH = f"{PARENT_FOLDER}/widget.js"


def _fake_changeset(changes: list[FileChange]) -> Changeset:
    return Changeset(
        owner="test-owner",
        repo="test-repo",
        target_sha="fake-sha-for-retention-test",
        baseline_sha="fake-baseline-for-retention-test",
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
def retention_repo():
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


def test_delete_then_revival_classifies_create_not_content_edit(retention_repo):
    session, repo = retention_repo
    client = get_confluence_client()

    # First sync: create the batch + section.
    changeset1 = _fake_changeset([
        FileChange(path=f"{PARENT_FOLDER}/index.js", status="added"),
        FileChange(path=SECTION_PATH, status="added"),
    ])
    records1 = build_approval_records(session, repo.id, changeset1)
    session.commit()

    mappings = {m.path: m for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()}
    parent_record = next(r for r in records1 if r.path_mapping_id == mappings[PARENT_FOLDER].id)
    section_record = next(r for r in records1 if r.path_mapping_id == mappings[SECTION_PATH].id)
    _approve_and_write(session, parent_record, "alice")
    _approve_and_write(session, section_record, "alice")

    session.refresh(mappings[SECTION_PATH])
    assert mappings[SECTION_PATH].removed_at is None
    batch_page_id = mappings[PARENT_FOLDER].page_id

    # Second sync: the section's file is removed while the batch's own file
    # is merely modified (not removed) -- so only the section itself should
    # classify DELETE, not the whole batch (which would otherwise suppress
    # the section-level DELETE as redundant, per _ensure_batch_page).
    changeset2 = _fake_changeset([
        FileChange(path=f"{PARENT_FOLDER}/index.js", status="modified"),
        FileChange(path=SECTION_PATH, status="removed"),
    ])
    records2 = build_approval_records(session, repo.id, changeset2)
    session.commit()
    delete_record = next(r for r in records2 if r.path_mapping_id == mappings[SECTION_PATH].id)
    assert delete_record.change_type == ChangeType.DELETE
    _approve_and_write(session, delete_record, "alice")

    session.refresh(mappings[SECTION_PATH])
    assert mappings[SECTION_PATH].removed_at is not None

    body = client.get_page(batch_page_id, include_body=True)["body"]["storage"]["value"]
    assert mappings[SECTION_PATH].section_anchor not in body

    # Third sync: the same file reappears -- must classify CREATE, not
    # CONTENT_EDIT (which would crash at write time against a section that's
    # already gone from the page body).
    changeset3 = _fake_changeset([FileChange(path=SECTION_PATH, status="added")])
    records3 = build_approval_records(session, repo.id, changeset3)
    session.commit()

    session.refresh(mappings[SECTION_PATH])
    assert mappings[SECTION_PATH].removed_at is None  # cleared by the revival in resolve_mapping

    revival_record = next(r for r in records3 if r.path_mapping_id == mappings[SECTION_PATH].id)
    assert revival_record.change_type == ChangeType.CREATE

    _approve_and_write(session, revival_record, "alice")  # must not raise SectionNotFoundError

    body_after = client.get_page(batch_page_id, include_body=True)["body"]["storage"]["value"]
    assert mappings[SECTION_PATH].section_anchor in body_after


def test_promoted_section_delete_actually_deletes_the_page(retention_repo):
    session, repo = retention_repo
    client = get_confluence_client()

    changeset = _fake_changeset([
        FileChange(path=f"{PARENT_FOLDER}/index.js", status="added"),
        FileChange(path=SECTION_PATH, status="added"),
    ])
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    mappings = {m.path: m for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()}
    parent_record = next(r for r in records if r.path_mapping_id == mappings[PARENT_FOLDER].id)
    section_record = next(r for r in records if r.path_mapping_id == mappings[SECTION_PATH].id)
    _approve_and_write(session, parent_record, "bob")
    _approve_and_write(session, section_record, "bob")

    # Manually promote: give the section its own real page, mirroring what
    # _write_promote does, without needing the full propose_promotion flow.
    section_mapping = mappings[SECTION_PATH]
    root = client.get_page(settings.confluence_root_page_id)
    promoted_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 retention promoted widget",
        html_body=f"<p>{section_mapping.section_anchor} promoted content</p>",
    )
    section_mapping.is_promoted = True
    section_mapping.page_id = promoted_page["id"]
    session.commit()

    delete_record = ApprovalRecord(
        path_mapping_id=section_mapping.id,
        change_type=ChangeType.DELETE,
        status=ApprovalStatus.PENDING,
    )
    session.add(delete_record)
    session.commit()
    _approve_and_write(session, delete_record, "bob")

    # The whole page must actually be gone now, not just emptied.
    trashed = client.get_page(promoted_page["id"])
    assert trashed["status"] == "trashed"

    session.refresh(section_mapping)
    assert section_mapping.page_id is None
    assert section_mapping.removed_at is not None


def test_successful_write_clears_content_and_sets_audit_summary(retention_repo):
    session, repo = retention_repo

    changeset = _fake_changeset([FileChange(path=f"{PARENT_FOLDER}/index.js", status="added")])
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    mapping = session.query(PathMapping).filter_by(repo_id=repo.id, path=PARENT_FOLDER).one()
    record = next(r for r in records if r.path_mapping_id == mapping.id)
    assert record.proposed_content  # real content before the write

    _approve_and_write(session, record, "carol")

    session.refresh(record)
    assert record.proposed_content is None
    assert record.current_content is None
    assert record.diff_patch is None
    assert record.pr_context is None

    audit_entry = (
        session.query(AuditLog)
        .filter_by(approval_record_id=record.id, action="write_succeeded")
        .one()
    )
    assert audit_entry.summary
    assert PARENT_FOLDER in audit_entry.summary


def test_failed_write_preserves_content_for_retry(retention_repo):
    session, repo = retention_repo

    changeset = _fake_changeset([FileChange(path=f"{PARENT_FOLDER}/index.js", status="added")])
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    mapping = session.query(PathMapping).filter_by(repo_id=repo.id, path=PARENT_FOLDER).one()
    record = next(r for r in records if r.path_mapping_id == mapping.id)
    original_content = record.proposed_content
    assert original_content

    # Force a write failure: repo.root_page_id pointed at a bogus id makes
    # the CREATE branch's client.get_page(parent_id) 404.
    real_root_page_id = repo.root_page_id
    repo.root_page_id = "999999999999"
    session.commit()

    record.status = ApprovalStatus.APPROVED
    record.approver = "dave"
    session.commit()
    with pytest.raises(Exception):
        write_approval(session, record.id)
    session.commit()

    session.refresh(record)
    session.refresh(mapping)
    assert mapping.sync_status == SyncStatus.FAILED
    assert record.proposed_content == original_content  # untouched, safe to retry

    repo.root_page_id = real_root_page_id
    session.commit()
