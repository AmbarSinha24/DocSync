from sqlalchemy.orm import Session

from app.engine import markers
from app.integrations.confluence import get_confluence_client
from app.models import ApprovalRecord, ApprovalStatus, ChangeType, PathMapping, SyncStatus


class ApprovalNotGrantedError(Exception):
    pass


def write_approval(db: Session, approval_id: int) -> None:
    """The hard-enforced gate: approval_id is a required positional argument,
    so there's no code path into this module that writes to Confluence without
    one. Also verifies at runtime that the record's status is actually
    APPROVED -- supplying *an* id isn't enough, it has to be an approved one.
    """
    approval = db.get(ApprovalRecord, approval_id)
    if approval is None:
        raise ApprovalNotGrantedError(f"no approval record with id {approval_id}")
    if approval.status != ApprovalStatus.APPROVED:
        raise ApprovalNotGrantedError(
            f"approval record {approval_id} has status {approval.status}, not APPROVED"
        )

    mapping = approval.path_mapping

    try:
        if mapping.parent_mapping_id is None:
            _write_page_level(approval, mapping)
        else:
            _write_section_level(approval, mapping)
        mapping.sync_status = SyncStatus.SYNCED
    except Exception:
        mapping.sync_status = SyncStatus.FAILED
        db.flush()
        raise

    db.flush()


def _write_page_level(approval: ApprovalRecord, mapping: PathMapping) -> None:
    """A batch-level page. Only CREATE is handled in Phase 2 -- batch-level
    delete/content-edit (e.g. a whole folder disappearing) are edge cases not
    yet built."""
    if approval.change_type != ChangeType.CREATE:
        raise NotImplementedError(f"page-level {approval.change_type} not yet supported")

    client = get_confluence_client()
    repo = mapping.repo
    root = client.get_page(repo.root_page_id)

    new_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=repo.root_page_id,
        title=mapping.title,
        html_body=approval.proposed_content or "",
    )
    mapping.page_id = new_page["id"]


def _write_section_level(approval: ApprovalRecord, mapping: PathMapping) -> None:
    parent = mapping.parent
    if parent is None or parent.page_id is None:
        raise ApprovalNotGrantedError(
            f"parent page for {mapping.path} hasn't been created yet -- "
            f"approve its CREATE first"
        )

    client = get_confluence_client()
    page = client.get_page(parent.page_id, include_body=True)
    body = page["body"]["storage"]["value"]
    version = page["version"]["number"]

    if approval.change_type == ChangeType.CREATE:
        new_section = markers.render_new_section(
            mapping.path, mapping.section_anchor, mapping.title, approval.proposed_content or ""
        )
        new_body = markers.insert_section(body, new_section)
    elif approval.change_type == ChangeType.CONTENT_EDIT:
        new_body = markers.replace_generated_block(
            body, mapping.section_anchor, approval.proposed_content or ""
        )
    elif approval.change_type == ChangeType.DELETE:
        new_body = markers.remove_section(body, mapping.section_anchor)
    else:
        raise NotImplementedError(f"section-level {approval.change_type} not yet supported")

    client.update_page(parent.page_id, page["title"], new_body, version)
