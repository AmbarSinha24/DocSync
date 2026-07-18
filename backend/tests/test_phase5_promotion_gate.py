import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.engine.confluence_writer import PROMOTION_CONTENT_LENGTH_THRESHOLD, write_approval
from app.integrations.confluence import get_confluence_client
from app.main import app
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

client = TestClient(app)

TEST_REPO_NAME = "test/phase5-promotion"
SECTION_ANCHOR = "sec-test-promotion"

LONG_CONTENT = "<p>" + ("word " * 900) + "</p>"  # comfortably over the threshold
SHORT_CONTENT = "<p>short</p>"

assert len(LONG_CONTENT) > PROMOTION_CONTENT_LENGTH_THRESHOLD


@pytest.fixture
def promotion_repo():
    session = SessionLocal()
    repo = Repo(
        name=TEST_REPO_NAME,
        source_type=RepoSourceType.GITHUB_APP,
        root_page_id=settings.confluence_root_page_id,
    )
    session.add(repo)
    session.flush()

    confluence_client = get_confluence_client()
    root = confluence_client.get_page(settings.confluence_root_page_id)
    batch_page = confluence_client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title="[test] phase5 promotion batch",
        html_body="<p>throwaway page for test_phase5_promotion_gate.py</p>",
    )

    batch_mapping = PathMapping(
        repo_id=repo.id, path="src/promo", title="Promo",
        page_id=batch_page["id"], sync_status=SyncStatus.SYNCED,
    )
    session.add(batch_mapping)
    session.flush()

    section_mapping = PathMapping(
        repo_id=repo.id, path="src/promo/big-thing", title="Big Thing",
        parent_mapping_id=batch_mapping.id, section_anchor=SECTION_ANCHOR,
        sync_status=SyncStatus.SYNCED,
    )
    session.add(section_mapping)
    session.flush()

    # Real CREATE write via write_approval (not a hand-rolled body) so the
    # is_promotable flag gets set through the actual production code path.
    create_record = ApprovalRecord(
        path_mapping_id=section_mapping.id,
        change_type=ChangeType.CREATE,
        proposed_content=LONG_CONTENT,
        status=ApprovalStatus.APPROVED,
        approver="fixture-setup",
    )
    session.add(create_record)
    session.flush()
    write_approval(session, create_record.id)
    session.commit()

    yield session, repo, batch_mapping, section_mapping, batch_page["id"]

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
            confluence_client.delete_page(page_id)
        except Exception:
            pass


def test_is_promotable_recomputed_not_latched(promotion_repo):
    session, _repo, _batch_mapping, section_mapping, _batch_page_id = promotion_repo

    session.refresh(section_mapping)
    assert section_mapping.is_promotable is True  # from the long CREATE in fixture setup

    # A follow-up short edit should flip it back off -- the signal tracks
    # current content, it doesn't latch true forever.
    shrink_record = ApprovalRecord(
        path_mapping_id=section_mapping.id,
        change_type=ChangeType.CONTENT_EDIT,
        proposed_content=SHORT_CONTENT,
        status=ApprovalStatus.APPROVED,
        approver="fixture-setup",
    )
    session.add(shrink_record)
    session.flush()
    write_approval(session, shrink_record.id)
    session.commit()

    session.refresh(section_mapping)
    assert section_mapping.is_promotable is False


def test_promote_endpoint_creates_own_page_and_future_edits_target_it(promotion_repo):
    session, _repo, batch_mapping, section_mapping, batch_page_id = promotion_repo

    propose_resp = client.post(f"/path-mappings/{section_mapping.id}/promote")
    assert propose_resp.status_code == 200
    promote_approval_id = propose_resp.json()["id"]
    assert propose_resp.json()["change_type"] == "promote"

    approve_resp = client.post(
        f"/approvals/{promote_approval_id}/approve", json={"actor": "erin"}
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["write_result"] == "synced"
    session.commit()

    session.refresh(section_mapping)
    assert section_mapping.is_promoted is True
    assert section_mapping.is_promotable is False
    assert section_mapping.page_id is not None
    assert section_mapping.page_id != batch_mapping.page_id

    confluence_client = get_confluence_client()
    new_page = confluence_client.get_page(section_mapping.page_id, include_body=True)
    assert SECTION_ANCHOR in new_page["body"]["storage"]["value"]

    old_parent_page = confluence_client.get_page(batch_page_id, include_body=True)
    assert SECTION_ANCHOR not in old_parent_page["body"]["storage"]["value"]  # cut out of the old page

    # A follow-up content edit on the now-promoted mapping must land on its
    # own page, not go looking for a parent that no longer holds its content.
    edit_record = ApprovalRecord(
        path_mapping_id=section_mapping.id,
        change_type=ChangeType.CONTENT_EDIT,
        proposed_content="<p>updated after promotion</p>",
        status=ApprovalStatus.APPROVED,
        approver="erin",
    )
    session.add(edit_record)
    session.flush()
    write_approval(session, edit_record.id)
    session.commit()

    updated_new_page = confluence_client.get_page(section_mapping.page_id, include_body=True)
    assert "updated after promotion" in updated_new_page["body"]["storage"]["value"]

    unchanged_old_page = confluence_client.get_page(batch_page_id, include_body=True)
    assert "updated after promotion" not in unchanged_old_page["body"]["storage"]["value"]


def test_promote_rejects_already_promoted_and_missing_mapping(promotion_repo):
    session, _repo, _batch_mapping, section_mapping, _batch_page_id = promotion_repo

    missing_resp = client.post("/path-mappings/999999999/promote")
    assert missing_resp.status_code == 404

    propose_resp = client.post(f"/path-mappings/{section_mapping.id}/promote")
    assert propose_resp.status_code == 200

    # A second promote request while the first is still pending should be rejected.
    duplicate_resp = client.post(f"/path-mappings/{section_mapping.id}/promote")
    assert duplicate_resp.status_code == 409
