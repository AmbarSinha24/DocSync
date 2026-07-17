import pytest

from app.config import settings
from app.db import SessionLocal
from app.engine.approval_builder import build_approval_records
from app.engine.confluence_writer import write_approval
from app.engine.core import generate_changeset
from app.engine.repo_state import resolve_baseline_sha
from app.engine.write_dispatcher import retry_failed, write_approved_records
from app.integrations.confluence import get_confluence_client
from app.models import (
    ApprovalRecord,
    ApprovalStatus,
    ChangeType,
    PathMapping,
    Repo,
    RepoSourceType,
    SyncStatus,
)

FIXTURE_OWNER = "AmbarSinha24"
FIXTURE_REPO = "docsync-fixture"
INITIAL_SHA = "e457ed87a419541171c945182bcefd2ba5ebfa16"
SECOND_SHA = "17636e4648d1499b37977718ee89d4aa36ad4364"
FIXTURE_ROOT_PAGE_ID = "950273"


@pytest.fixture
def committing_db():
    """A real, auto-committing session for tests whose code under test calls
    commit()/rollback() itself (write_approval, write_approved_records) --
    that doesn't compose with the rollback-only `db` fixture used for pure
    constraint tests, since a nested commit against an externally-begun
    transaction doesn't actually persist. Cleans up its own rows + any
    Confluence pages created, tracked via the yielded lists."""
    session = SessionLocal()
    repo_ids: list[int] = []
    page_ids: list[str] = []
    yield session, repo_ids, page_ids

    client = get_confluence_client()
    for page_id in page_ids:
        try:
            client.delete_page(page_id)
        except Exception:
            pass
    for repo_id in repo_ids:
        mapping_ids = [m.id for m in session.query(PathMapping).filter_by(repo_id=repo_id).all()]
        session.query(ApprovalRecord).filter(
            ApprovalRecord.path_mapping_id.in_(mapping_ids)
        ).delete(synchronize_session=False)
        session.query(PathMapping).filter(
            PathMapping.repo_id == repo_id, PathMapping.parent_mapping_id.isnot(None)
        ).delete(synchronize_session=False)
        session.query(PathMapping).filter(
            PathMapping.repo_id == repo_id, PathMapping.parent_mapping_id.is_(None)
        ).delete(synchronize_session=False)
        session.query(Repo).filter_by(id=repo_id).delete()
    session.commit()
    session.close()


def test_first_push_resolves_null_baseline(db):
    repo, baseline = resolve_baseline_sha(db, "some-owner", "brand-new-repo")
    assert baseline is None
    assert repo.last_synced_sha is None

    repo.last_synced_sha = "abc123"
    db.flush()

    repo2, baseline2 = resolve_baseline_sha(db, "some-owner", "brand-new-repo")
    assert repo2.id == repo.id
    assert baseline2 == "abc123"


def test_confluence_writer_requires_approval_id_argument():
    with pytest.raises(TypeError):
        write_approval(db=None)  # type: ignore[call-arg]


def test_partial_failure_isolated_and_retry_reprocesses_only_failed(committing_db):
    session, repo_ids, page_ids = committing_db
    client = get_confluence_client()
    root = client.get_page(settings.confluence_root_page_id)

    ok_page = client.create_page(
        root["spaceId"], settings.confluence_root_page_id, "Gate Test - OK Batch", "<p>x</p>"
    )
    page_ids.append(ok_page["id"])

    repo = Repo(
        name="test/phase2-gate-partial-failure",
        source_type=RepoSourceType.GITHUB_APP,
        root_page_id=settings.confluence_root_page_id,
    )
    session.add(repo)
    session.flush()
    repo_ids.append(repo.id)

    batch_ok = PathMapping(repo_id=repo.id, path="ok", title="OK", page_id=ok_page["id"])
    batch_fail = PathMapping(repo_id=repo.id, path="fail", title="Fail", page_id=None)
    session.add_all([batch_ok, batch_fail])
    session.flush()

    section_ok = PathMapping(
        repo_id=repo.id, path="ok/a", title="A", parent_mapping_id=batch_ok.id, section_anchor="sec-a"
    )
    section_fail = PathMapping(
        repo_id=repo.id, path="fail/b", title="B", parent_mapping_id=batch_fail.id, section_anchor="sec-b"
    )
    session.add_all([section_ok, section_fail])
    session.flush()

    approval_ok = ApprovalRecord(
        path_mapping_id=section_ok.id, change_type=ChangeType.CREATE,
        proposed_content="<p>ok</p>", status=ApprovalStatus.APPROVED,
    )
    approval_fail = ApprovalRecord(
        path_mapping_id=section_fail.id, change_type=ChangeType.CREATE,
        proposed_content="<p>fail</p>", status=ApprovalStatus.APPROVED,
    )
    session.add_all([approval_ok, approval_fail])
    session.commit()

    results = write_approved_records(session, [approval_ok.id, approval_fail.id])
    session.refresh(section_ok)
    session.refresh(section_fail)

    assert results == {approval_ok.id: "synced", approval_fail.id: "failed"}
    assert section_ok.sync_status == SyncStatus.SYNCED
    assert section_fail.sync_status == SyncStatus.FAILED

    fail_page = client.create_page(
        root["spaceId"], settings.confluence_root_page_id, "Gate Test - Fail Batch (fixed)", "<p>x</p>"
    )
    page_ids.append(fail_page["id"])
    batch_fail.page_id = fail_page["id"]
    session.commit()

    retry_results = retry_failed(session, repo.id)
    session.refresh(section_ok)
    session.refresh(section_fail)

    assert list(retry_results.keys()) == [approval_fail.id]
    assert section_fail.sync_status == SyncStatus.SYNCED


@pytest.mark.asyncio
async def test_end_to_end_content_edit_writes_real_confluence_markers(committing_db):
    session, repo_ids, page_ids = committing_db

    repo = Repo(
        name="test/phase2-gate-e2e",
        source_type=RepoSourceType.GITHUB_APP,
        root_page_id=FIXTURE_ROOT_PAGE_ID,
        last_synced_sha=INITIAL_SHA,
    )
    session.add(repo)
    session.flush()
    repo_ids.append(repo.id)

    client = get_confluence_client()
    root = client.get_page(FIXTURE_ROOT_PAGE_ID)
    batch_page = client.create_page(
        root["spaceId"], FIXTURE_ROOT_PAGE_ID, "Gate Test - Billing Batch", "<p>overview</p>"
    )
    page_ids.append(batch_page["id"])

    # Level-2 batch key for src/services/billing/invoice.py is "src/services";
    # the section key (immediate child of the batch folder) is "src/services/billing".
    batch_mapping = PathMapping(
        repo_id=repo.id, path="src/services", title="Services",
        page_id=batch_page["id"],
    )
    session.add(batch_mapping)
    session.flush()

    section_mapping = PathMapping(
        repo_id=repo.id, path="src/services/billing", title="Billing Service",
        parent_mapping_id=batch_mapping.id, section_anchor="sec-e2e-invoice",
    )
    session.add(section_mapping)
    session.flush()

    section_html = (
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        '<ac:parameter ac:name="">sec-e2e-invoice-section-start</ac:parameter></ac:structured-macro>\n'
        "<h2>Invoice</h2>\n\n"
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        '<ac:parameter ac:name="">sec-e2e-invoice-gen-start</ac:parameter></ac:structured-macro>\n'
        "<p>original invoice content</p>\n"
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        '<ac:parameter ac:name="">sec-e2e-invoice-gen-end</ac:parameter></ac:structured-macro>\n'
        '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
        '<ac:parameter ac:name="">sec-e2e-invoice-section-end</ac:parameter></ac:structured-macro>'
    )
    fetched = client.get_page(batch_page["id"], include_body=True)
    client.update_page(batch_page["id"], fetched["title"], section_html, fetched["version"]["number"])
    session.commit()

    changeset = await generate_changeset(FIXTURE_OWNER, FIXTURE_REPO, SECOND_SHA, INITIAL_SHA)
    records = build_approval_records(session, repo.id, changeset)
    session.commit()

    billing_records = [r for r in records if r.path_mapping.path == "src/services/billing"]
    assert len(billing_records) == 1
    approval = billing_records[0]
    assert approval.change_type == ChangeType.CONTENT_EDIT

    approval.status = ApprovalStatus.APPROVED
    session.commit()
    result = write_approved_records(session, [approval.id])
    assert result[approval.id] == "synced"

    final = client.get_page(batch_page["id"], include_body=True)
    body = final["body"]["storage"]["value"]
    assert "sec-e2e-invoice" in body
    assert "original invoice content" not in body  # GENERATED block was replaced
    assert "<h2>Invoice</h2>" in body  # title outside GENERATED survived untouched
