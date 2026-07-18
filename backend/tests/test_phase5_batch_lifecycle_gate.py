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

TEST_REPO_NAME = "test/phase5-batch-lifecycle"


def _fake_changeset(changes: list[FileChange]) -> Changeset:
    return Changeset(
        owner="test-owner",
        repo="test-repo",
        target_sha="fake-sha-for-batch-lifecycle-test",
        baseline_sha="fake-baseline-for-batch-lifecycle-test",
        changes=changes,
    )


@pytest.fixture
def lifecycle_repo():
    """A real, auto-committing session. Every batch page in this fixture is
    created through the real write_approval CREATE path (not hand-rolled
    HTML), so each one naturally gets the anchor-wrapped overview this
    feature depends on -- except the deliberately-legacy one, which is
    hand-rolled without a wrapper on purpose, to test the self-healing
    fallback for pages that predate this change."""
    session = SessionLocal()
    repo = Repo(
        name=TEST_REPO_NAME,
        source_type=RepoSourceType.GITHUB_APP,
        root_page_id=settings.confluence_root_page_id,
    )
    session.add(repo)
    session.flush()

    def _create_real_batch(batch_key: str, title: str) -> PathMapping:
        # resolve_mapping (the real production path) always sets
        # section_anchor -- this bypasses it to construct the row directly,
        # so it has to set one too, or write_approval's anchor-macro
        # rendering blows up on None + str.
        mapping = PathMapping(
            repo_id=repo.id, path=batch_key, title=title, sync_status=SyncStatus.SYNCED,
            section_anchor=f"sec-test-lifecycle-{batch_key.rsplit('/', 1)[-1]}",
        )
        session.add(mapping)
        session.flush()
        record = ApprovalRecord(
            path_mapping_id=mapping.id,
            change_type=ChangeType.CREATE,
            proposed_content=f"<p>{title} overview</p>",
            status=ApprovalStatus.APPROVED,
            approver="fixture-setup",
        )
        session.add(record)
        session.flush()
        write_approval(session, record.id)
        return mapping

    edit_batch = _create_real_batch("src/edit-target", "Edit Target")
    delete_batch = _create_real_batch("src/delete-target", "Delete Target")
    promo_batch = _create_real_batch("src/promo-target", "Promo Target")

    edit_section = PathMapping(
        repo_id=repo.id, path="src/edit-target/existing", title="Existing",
        parent_mapping_id=edit_batch.id, section_anchor="sec-test-lifecycle-existing",
        sync_status=SyncStatus.SYNCED,
    )
    delete_section = PathMapping(
        repo_id=repo.id, path="src/delete-target/only-thing", title="Only Thing",
        parent_mapping_id=delete_batch.id, section_anchor="sec-test-lifecycle-only",
        sync_status=SyncStatus.SYNCED,
    )
    promoted_section = PathMapping(
        repo_id=repo.id, path="src/promo-target/independent", title="Independent",
        parent_mapping_id=promo_batch.id, section_anchor="sec-test-lifecycle-promoted",
        sync_status=SyncStatus.SYNCED, is_promoted=True,
    )
    session.add_all([edit_section, delete_section, promoted_section])
    session.flush()

    client = get_confluence_client()

    for batch, section in [(edit_batch, edit_section), (delete_batch, delete_section)]:
        record = ApprovalRecord(
            path_mapping_id=section.id, change_type=ChangeType.CREATE,
            proposed_content=f"<p>original {section.title} content</p>",
            status=ApprovalStatus.APPROVED, approver="fixture-setup",
        )
        session.add(record)
        session.flush()
        write_approval(session, record.id)

    promoted_page = client.create_page(
        space_id=client.get_page(settings.confluence_root_page_id)["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 batch lifecycle promoted section",
        html_body=(
            '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
            '<ac:parameter ac:name="">sec-test-lifecycle-promoted-section-start</ac:parameter></ac:structured-macro>\n'
            "<h2>Independent</h2>\n\n"
            '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
            '<ac:parameter ac:name="">sec-test-lifecycle-promoted-gen-start</ac:parameter></ac:structured-macro>\n'
            "<p>independent content</p>\n"
            '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
            '<ac:parameter ac:name="">sec-test-lifecycle-promoted-gen-end</ac:parameter></ac:structured-macro>\n'
            '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
            '<ac:parameter ac:name="">sec-test-lifecycle-promoted-section-end</ac:parameter></ac:structured-macro>'
        ),
    )
    promoted_section.page_id = promoted_page["id"]

    # A legacy batch page, hand-rolled WITHOUT the anchor wrap -- simulates a
    # page created before this feature existed.
    legacy_page = client.create_page(
        space_id=client.get_page(settings.confluence_root_page_id)["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 batch lifecycle legacy batch",
        html_body="<p>legacy overview with no anchor wrapper at all</p>",
    )
    legacy_batch = PathMapping(
        repo_id=repo.id, path="src/legacy-target", title="Legacy Target",
        page_id=legacy_page["id"], section_anchor="sec-test-lifecycle-legacy-batch",
        sync_status=SyncStatus.SYNCED,
    )
    session.add(legacy_batch)
    session.commit()

    yield session, repo, edit_batch, edit_section, delete_batch, delete_section, promo_batch, promoted_section, legacy_batch

    session.rollback()

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

    for page_id in page_ids:
        try:
            client.delete_page(page_id)
        except Exception:
            pass


def test_batch_content_edit_refreshes_overview_without_touching_sections(lifecycle_repo):
    session, repo, edit_batch, edit_section, *_rest = lifecycle_repo
    client = get_confluence_client()

    before = client.get_page(edit_batch.page_id, include_body=True)
    assert "sec-test-lifecycle-existing" in before["body"]["storage"]["value"]

    changeset = _fake_changeset(
        [FileChange(path="src/edit-target/existing/new_file.py", status="added")]
    )
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    batch_records = [r for r in records if r.path_mapping_id == edit_batch.id]
    assert len(batch_records) == 1
    assert batch_records[0].change_type == ChangeType.CONTENT_EDIT

    batch_records[0].status = ApprovalStatus.APPROVED
    batch_records[0].approver = "frank"
    session.commit()
    write_approval(session, batch_records[0].id)
    session.commit()

    after = client.get_page(edit_batch.page_id, include_body=True)
    body = after["body"]["storage"]["value"]
    assert "sec-test-lifecycle-existing" in body  # child section untouched
    assert "original Existing content" in body  # child section content untouched


def test_batch_delete_suppresses_redundant_section_delete(lifecycle_repo):
    session, repo, _eb, _es, delete_batch, delete_section, *_rest = lifecycle_repo
    client = get_confluence_client()
    original_page_id = delete_batch.page_id

    changeset = _fake_changeset(
        [FileChange(path="src/delete-target/only-thing/gone.py", status="removed")]
    )
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    batch_records = [r for r in records if r.path_mapping_id == delete_batch.id]
    assert len(batch_records) == 1
    assert batch_records[0].change_type == ChangeType.DELETE

    # No separate section-level DELETE for the section covered by the batch delete.
    assert not any(r.path_mapping_id == delete_section.id for r in records)

    batch_records[0].status = ApprovalStatus.APPROVED
    batch_records[0].approver = "grace"
    session.commit()
    write_approval(session, batch_records[0].id)
    session.commit()

    session.refresh(delete_batch)
    assert delete_batch.page_id is None  # bookkeeping cleared

    # Confluence's page delete is a soft-delete (moves to trash) -- the page
    # stays fetchable by id, just no longer "current".
    trashed = client.get_page(original_page_id, include_body=True)
    assert trashed["status"] == "trashed"


def test_promoted_section_still_gets_own_delete_when_batch_deleted(lifecycle_repo):
    session, repo, *_rest, promo_batch, promoted_section, _legacy = lifecycle_repo

    # The promoted section's own underlying file is removed too, in the SAME
    # sync as its batch going empty -- this is exactly the case the
    # suppression logic needs to make an exception for.
    changeset = _fake_changeset(
        [FileChange(path="src/promo-target/independent/thing.py", status="removed")]
    )
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    batch_records = [r for r in records if r.path_mapping_id == promo_batch.id]
    assert len(batch_records) == 1
    assert batch_records[0].change_type == ChangeType.DELETE

    # Unlike a normal section, the promoted one still gets its own DELETE
    # proposal -- it lives on its own page, unaffected by the batch page
    # disappearing, so suppressing it would silently leave it undocumented.
    section_records = [r for r in records if r.path_mapping_id == promoted_section.id]
    assert len(section_records) == 1
    assert section_records[0].change_type == ChangeType.DELETE


def test_legacy_batch_page_self_heals_on_content_edit(lifecycle_repo):
    session, repo, *_rest, legacy_batch = lifecycle_repo
    client = get_confluence_client()

    before = client.get_page(legacy_batch.page_id, include_body=True)
    assert "legacy overview with no anchor wrapper at all" in before["body"]["storage"]["value"]

    record = ApprovalRecord(
        path_mapping_id=legacy_batch.id,
        change_type=ChangeType.CONTENT_EDIT,
        proposed_content="<p>freshly healed overview</p>",
        status=ApprovalStatus.APPROVED,
        approver="heidi",
    )
    session.add(record)
    session.flush()

    write_approval(session, record.id)  # must not raise SectionNotFoundError
    session.commit()

    after = client.get_page(legacy_batch.page_id, include_body=True)
    body = after["body"]["storage"]["value"]
    assert "freshly healed overview" in body
    assert legacy_batch.section_anchor in body
