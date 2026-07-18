import pytest

from app.config import settings
from app.db import SessionLocal
from app.engine.approval_builder import build_approval_records
from app.engine.models import Changeset, FileChange
from app.engine.write_dispatcher import write_approved_records
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

TEST_REPO_NAME = "test/phase5-rename-detection"

# Same batch ("src/services") on both sides -- should be auto-detected and
# relocated in place.
OLD_SAME_BATCH_SECTION_PATH = "src/services/auth"
NEW_SAME_BATCH_SECTION_PATH = "src/services/authentication"

# Different batch on each side ("src/services" -> "docs/services") -- the
# anchored content has to physically move from the old batch page to the new
# one (see confluence_writer._write_rename).
OLD_CROSS_BATCH_SECTION_PATH = "src/services/billing"
NEW_CROSS_BATCH_SECTION_PATH = "docs/services/billing"
NEW_BATCH_KEY = "docs/services"

SECTION_ANCHOR = "sec-test-rename-auth"
BILLING_ANCHOR = "sec-test-rename-billing"


def _fake_changeset(changes: list[FileChange]) -> Changeset:
    """GitHub's real rename heuristic can't be reliably triggered through the
    available write tools (same limitation noted in
    test_engine_phase1.py::test_rename_status_aggregated_as_a_move_not_delete_add),
    so this fabricates a Changeset directly against GitHub's documented
    response shape instead of going through generate_changeset. Everything
    downstream of that (build_approval_records, the real DB, the real
    Confluence writes) is exercised for real."""
    return Changeset(
        owner="test-owner",
        repo="test-repo",
        target_sha="fake-sha-for-rename-test",
        baseline_sha="fake-baseline-for-rename-test",
        changes=changes,
    )


def _section_html(anchor: str, title: str, content: str) -> str:
    return (
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{anchor}-section-start</ac:parameter></ac:structured-macro>\n'
        f"<h2>{title}</h2>\n\n"
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{anchor}-gen-start</ac:parameter></ac:structured-macro>\n'
        f"{content}\n"
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{anchor}-gen-end</ac:parameter></ac:structured-macro>\n'
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{anchor}-section-end</ac:parameter></ac:structured-macro>'
    )


@pytest.fixture
def rename_repo():
    """A real, auto-committing session (build_approval_records/write_approval
    commit internally). Seeds a source batch page with two already-synced,
    real anchored sections (one for the same-batch rename case, one for the
    cross-batch case), plus a second, empty destination batch page the
    cross-batch case moves content into. Cleans up all rows + any Confluence
    pages created during the test."""
    session = SessionLocal()
    repo = Repo(name=TEST_REPO_NAME, source_type=RepoSourceType.GITHUB_APP)
    session.add(repo)
    session.flush()

    client = get_confluence_client()
    root = client.get_page(settings.confluence_root_page_id)
    batch_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 rename detection batch",
        html_body="<p>throwaway page for test_phase5_rename_gate.py</p>",
    )
    dest_batch_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 rename detection destination batch",
        html_body="<p>throwaway destination page for test_phase5_rename_gate.py</p>",
    )

    batch_mapping = PathMapping(
        repo_id=repo.id,
        path="src/services",
        title="Services",
        page_id=batch_page["id"],
        sync_status=SyncStatus.SYNCED,
    )
    dest_batch_mapping = PathMapping(
        repo_id=repo.id,
        path=NEW_BATCH_KEY,
        title="Docs Services",
        page_id=dest_batch_page["id"],
        sync_status=SyncStatus.SYNCED,
    )
    session.add_all([batch_mapping, dest_batch_mapping])
    session.flush()

    section_mapping = PathMapping(
        repo_id=repo.id,
        path=OLD_SAME_BATCH_SECTION_PATH,
        title="Auth",
        parent_mapping_id=batch_mapping.id,
        section_anchor=SECTION_ANCHOR,
        sync_status=SyncStatus.SYNCED,
    )
    cross_batch_source = PathMapping(
        repo_id=repo.id,
        path=OLD_CROSS_BATCH_SECTION_PATH,
        title="Billing",
        parent_mapping_id=batch_mapping.id,
        section_anchor=BILLING_ANCHOR,
        sync_status=SyncStatus.SYNCED,
    )
    session.add_all([section_mapping, cross_batch_source])
    session.flush()

    combined_body = (
        _section_html(SECTION_ANCHOR, "Auth", "<p>original auth content</p>")
        + "\n\n"
        + _section_html(BILLING_ANCHOR, "Billing", "<p>original billing content</p>")
    )
    fetched = client.get_page(batch_page["id"], include_body=True)
    client.update_page(batch_page["id"], fetched["title"], combined_body, fetched["version"]["number"])
    session.commit()

    yield session, repo, section_mapping, cross_batch_source, batch_page["id"], dest_batch_page["id"]

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

    for page_id in page_ids:
        try:
            client.delete_page(page_id)
        except Exception:
            pass


def test_same_batch_rename_relocates_mapping_without_touching_confluence(rename_repo):
    session, repo, section_mapping, _cross_batch_source, batch_page_id, _dest_batch_page_id = rename_repo

    client = get_confluence_client()
    before = client.get_page(batch_page_id, include_body=True)

    changeset = _fake_changeset(
        [
            FileChange(
                path=f"{NEW_SAME_BATCH_SECTION_PATH}/login.py",
                status="renamed",
                previous_path=f"{OLD_SAME_BATCH_SECTION_PATH}/login.py",
            )
        ]
    )

    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    rename_records = [r for r in records if r.path_mapping_id == section_mapping.id]
    assert len(rename_records) == 1
    record = rename_records[0]
    assert record.change_type == ChangeType.RENAME
    assert record.proposed_location == NEW_SAME_BATCH_SECTION_PATH
    assert record.proposed_content is not None  # snapshotted, even though same-batch never writes it anywhere

    record.status = ApprovalStatus.APPROVED
    session.commit()
    result = write_approved_records(session, [record.id])
    assert result[record.id] == "synced"

    session.refresh(section_mapping)
    assert section_mapping.path == NEW_SAME_BATCH_SECTION_PATH
    assert section_mapping.sync_status == SyncStatus.SYNCED

    after = client.get_page(batch_page_id, include_body=True)
    assert after["version"]["number"] == before["version"]["number"]  # no Confluence write happened
    assert after["body"]["storage"]["value"] == before["body"]["storage"]["value"]


def test_cross_batch_rename_moves_content_between_pages(rename_repo):
    session, repo, _section_mapping, cross_batch_source, batch_page_id, dest_batch_page_id = rename_repo

    changeset = _fake_changeset(
        [
            FileChange(
                path=f"{NEW_CROSS_BATCH_SECTION_PATH}/invoice.py",
                status="renamed",
                previous_path=f"{OLD_CROSS_BATCH_SECTION_PATH}/invoice.py",
            )
        ]
    )

    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    rename_records = [r for r in records if r.path_mapping_id == cross_batch_source.id]
    assert len(rename_records) == 1
    record = rename_records[0]
    assert record.change_type == ChangeType.RENAME
    assert record.proposed_location == NEW_CROSS_BATCH_SECTION_PATH
    assert "original billing content" in (record.proposed_content or "")

    # No plain CREATE snuck in for the new path -- it's a move, not a fresh page.
    assert not any(
        r.change_type == ChangeType.CREATE and r.proposed_location == NEW_CROSS_BATCH_SECTION_PATH
        for r in records
    )

    record.status = ApprovalStatus.APPROVED
    session.commit()
    result = write_approved_records(session, [record.id])
    assert result[record.id] == "synced"

    session.refresh(cross_batch_source)
    assert cross_batch_source.path == NEW_CROSS_BATCH_SECTION_PATH
    assert cross_batch_source.parent_mapping_id != session.query(PathMapping).filter_by(
        repo_id=repo.id, path="src/services"
    ).one().id
    assert cross_batch_source.sync_status == SyncStatus.SYNCED

    client = get_confluence_client()
    old_page = client.get_page(batch_page_id, include_body=True)
    assert BILLING_ANCHOR not in old_page["body"]["storage"]["value"]  # cut out of the old page

    new_page = client.get_page(dest_batch_page_id, include_body=True)
    assert BILLING_ANCHOR in new_page["body"]["storage"]["value"]
    assert "original billing content" in new_page["body"]["storage"]["value"]  # moved as-is


def test_cross_batch_rename_to_nonexistent_destination_fails_cleanly(rename_repo):
    session, repo, _section_mapping, _cross_batch_source, _batch_page_id, _dest_batch_page_id = rename_repo

    # "archive/services" was never created in the fixture -- the destination
    # batch page has to exist (its own CREATE approved) before a section can
    # move into it, same dependency ordering a normal section create needs.
    stray_source = PathMapping(
        repo_id=repo.id,
        path="src/services/legacy",
        title="Legacy",
        parent_mapping_id=session.query(PathMapping).filter_by(repo_id=repo.id, path="src/services").one().id,
        section_anchor="sec-test-rename-legacy",
        sync_status=SyncStatus.SYNCED,
    )
    session.add(stray_source)
    session.commit()

    changeset = _fake_changeset(
        [
            FileChange(
                path="archive/services/legacy/old.py",
                status="renamed",
                previous_path="src/services/legacy/old.py",
            )
        ]
    )

    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    rename_records = [r for r in records if r.path_mapping_id == stray_source.id]
    assert len(rename_records) == 1
    record = rename_records[0]

    record.status = ApprovalStatus.APPROVED
    session.commit()
    result = write_approved_records(session, [record.id])
    assert result[record.id] == "failed"

    session.refresh(stray_source)
    assert stray_source.path == "src/services/legacy"  # untouched -- the failed write didn't corrupt anything
    assert stray_source.sync_status == SyncStatus.FAILED
