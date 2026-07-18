import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.integrations.confluence import get_confluence_client
from app.main import app
from app.models import (
    ApprovalRecord,
    ApprovalStatus,
    AuditAction,
    AuditLog,
    ChangeType,
    PathMapping,
    Repo,
    RepoSourceType,
    SyncStatus,
)

client = TestClient(app)

TEST_REPO_NAME = "test/phase5-audit-trail"
SECTION_ANCHOR = "sec-test-audit-content"


@pytest.fixture
def audit_repo():
    """A real repo with one real, live-in-Confluence CONTENT_EDIT section (for
    the edit/regenerate/approve flow) and one section under a batch with a
    deliberately bogus page_id (so approving it forces a real write failure).
    Cleans up all rows + any real Confluence pages created."""
    session = SessionLocal()
    repo = Repo(name=TEST_REPO_NAME, source_type=RepoSourceType.GITHUB_APP)
    session.add(repo)
    session.flush()

    confluence_client = get_confluence_client()
    root = confluence_client.get_page(settings.confluence_root_page_id)
    batch_page = confluence_client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 audit trail batch",
        html_body="<p>throwaway page for test_phase5_audit_gate.py</p>",
    )

    batch_mapping = PathMapping(
        repo_id=repo.id, path="src/audit", title="Audit",
        page_id=batch_page["id"], sync_status=SyncStatus.SYNCED,
    )
    broken_batch_mapping = PathMapping(
        repo_id=repo.id, path="src/broken", title="Broken",
        page_id="000000",  # a page id guaranteed not to exist
        sync_status=SyncStatus.SYNCED,
    )
    session.add_all([batch_mapping, broken_batch_mapping])
    session.flush()

    section_mapping = PathMapping(
        repo_id=repo.id, path="src/audit/thing", title="Thing",
        parent_mapping_id=batch_mapping.id, section_anchor=SECTION_ANCHOR,
        sync_status=SyncStatus.SYNCED,
    )
    broken_section_mapping = PathMapping(
        repo_id=repo.id, path="src/broken/thing", title="Broken Thing",
        parent_mapping_id=broken_batch_mapping.id, section_anchor="sec-test-audit-broken",
        sync_status=SyncStatus.SYNCED,
    )
    session.add_all([section_mapping, broken_section_mapping])
    session.flush()

    section_html = (
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{SECTION_ANCHOR}-section-start</ac:parameter></ac:structured-macro>\n'
        "<h2>Thing</h2>\n\n"
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{SECTION_ANCHOR}-gen-start</ac:parameter></ac:structured-macro>\n'
        "<p>original thing content</p>\n"
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{SECTION_ANCHOR}-gen-end</ac:parameter></ac:structured-macro>\n'
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        f'<ac:parameter ac:name="">{SECTION_ANCHOR}-section-end</ac:parameter></ac:structured-macro>'
    )
    fetched = confluence_client.get_page(batch_page["id"], include_body=True)
    confluence_client.update_page(batch_page["id"], fetched["title"], section_html, fetched["version"]["number"])

    editable_record = ApprovalRecord(
        path_mapping_id=section_mapping.id,
        change_type=ChangeType.CONTENT_EDIT,
        proposed_content="<p>proposed v1</p>",
        current_content="<p>original thing content</p>",
        diff_patch="--- src/audit/thing (modified)\nfake diff for test",
        commit_sha="fake-sha-for-audit-test",
        status=ApprovalStatus.PENDING,
    )
    failing_record = ApprovalRecord(
        path_mapping_id=broken_section_mapping.id,
        change_type=ChangeType.CONTENT_EDIT,
        proposed_content="<p>doesn't matter, write will fail</p>",
        diff_patch="--- src/broken/thing (modified)\nfake diff for test",
        commit_sha="fake-sha-for-audit-test",
        status=ApprovalStatus.PENDING,
    )
    session.add_all([editable_record, failing_record])
    session.commit()

    yield session, repo, editable_record, failing_record, batch_page["id"]

    session.rollback()

    page_ids = {
        m.page_id
        for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()
        if m.page_id and m.page_id != "000000"
    }
    mapping_ids = [m.id for m in session.query(PathMapping).filter_by(repo_id=repo.id).all()]
    if mapping_ids:
        session.query(AuditLog).filter(
            AuditLog.approval_record_id.in_(
                [a.id for a in session.query(ApprovalRecord).filter(
                    ApprovalRecord.path_mapping_id.in_(mapping_ids)
                ).all()]
            )
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
            confluence_client.delete_page(page_id)
        except Exception:
            pass


def test_edit_and_regenerate_snapshot_previous_values_in_audit_log(audit_repo):
    session, _repo, editable_record, _failing_record, _batch_page_id = audit_repo

    edit_resp = client.patch(
        f"/approvals/{editable_record.id}",
        json={"actor": "alice", "proposed_content": "<p>proposed v2</p>"},
    )
    assert edit_resp.status_code == 200
    session.commit()  # close out session's pinned REPEATABLE READ snapshot so the next query sees the other session's commit

    edit_audit = (
        session.query(AuditLog)
        .filter_by(approval_record_id=editable_record.id, action=AuditAction.EDITED)
        .one()
    )
    assert edit_audit.actor == "alice"
    assert edit_audit.previous_content == "<p>proposed v1</p>"
    assert edit_audit.previous_name is None  # proposed_name was never touched

    regen_resp = client.post(
        f"/approvals/{editable_record.id}/regenerate",
        json={"actor": "bob", "feedback": "make it shorter"},
    )
    assert regen_resp.status_code == 200
    session.commit()

    regen_audit = (
        session.query(AuditLog)
        .filter_by(approval_record_id=editable_record.id, action=AuditAction.REGENERATED)
        .one()
    )
    assert regen_audit.actor == "bob"
    assert regen_audit.previous_content == "<p>proposed v2</p>"  # the value right before regen overwrote it


def test_approve_logs_write_succeeded_and_a_broken_write_logs_write_failed(audit_repo):
    session, _repo, editable_record, failing_record, batch_page_id = audit_repo

    approve_resp = client.post(f"/approvals/{editable_record.id}/approve", json={"actor": "carol"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["write_result"] == "synced"
    session.commit()

    write_audit = (
        session.query(AuditLog)
        .filter_by(approval_record_id=editable_record.id, action=AuditAction.WRITE_SUCCEEDED)
        .one()
    )
    assert write_audit.actor == "carol"

    confluence_client = get_confluence_client()
    final = confluence_client.get_page(batch_page_id, include_body=True)
    assert "<p>proposed v1</p>" in final["body"]["storage"]["value"]  # the real write actually happened

    fail_resp = client.post(f"/approvals/{failing_record.id}/approve", json={"actor": "dave"})
    assert fail_resp.status_code == 200
    assert fail_resp.json()["write_result"] == "failed"
    session.commit()

    fail_audit = (
        session.query(AuditLog)
        .filter_by(approval_record_id=failing_record.id, action=AuditAction.WRITE_FAILED)
        .one()
    )
    assert fail_audit.actor == "dave"

    session.refresh(failing_record)
    assert failing_record.path_mapping.sync_status == SyncStatus.FAILED
