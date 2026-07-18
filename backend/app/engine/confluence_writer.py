from sqlalchemy.orm import Session

from app.engine import markers
from app.engine.batcher import _batch_key_for_path
from app.integrations.confluence import get_confluence_client
from app.models import (
    ApprovalRecord,
    ApprovalStatus,
    AuditAction,
    AuditLog,
    ChangeType,
    PathMapping,
    SyncStatus,
)

# Chars of rendered GENERATED content past which a section is flagged as a
# candidate for promotion to its own top-level page. A rough heuristic, not a
# hard rule -- promotion always needs an explicit human confirm regardless
# (see propose_promotion in app/routers/repos.py), this only decides when to
# surface the option.
PROMOTION_CONTENT_LENGTH_THRESHOLD = 4000


class ApprovalNotGrantedError(Exception):
    pass


def resolve_content_page_id(mapping: PathMapping) -> str | None:
    """Where this mapping's own anchored content physically lives: its own
    page if it's a batch/page-level mapping (parent_mapping_id is None) or
    has been promoted, otherwise inside its parent batch page's body.
    Shared by the writer (to know what to update) and the approval builder
    (to fetch current content for a diff) so the two can't drift apart on
    what "promoted" and "batch-level" mean for page resolution."""
    if mapping.parent_mapping_id is None or mapping.is_promoted:
        return mapping.page_id
    return mapping.parent.page_id if mapping.parent else None


def write_approval(db: Session, approval_id: int) -> None:
    """The hard-enforced gate: approval_id is a required positional argument,
    so there's no code path into this module that writes to Confluence without
    one. Also verifies at runtime that the record's status is actually
    APPROVED -- supplying *an* id isn't enough, it has to be an approved one.

    Every write attempt gets its own AuditLog entry (WRITE_SUCCEEDED or
    WRITE_FAILED), independent of mapping.sync_status. sync_status only ever
    holds the *current* state, so a failed attempt followed by a successful
    retry would otherwise leave no trace that the first attempt ever failed --
    the audit log is the durable, append-only record of that history.
    """
    approval = db.get(ApprovalRecord, approval_id)
    if approval is None:
        raise ApprovalNotGrantedError(f"no approval record with id {approval_id}")
    if approval.status != ApprovalStatus.APPROVED:
        raise ApprovalNotGrantedError(
            f"approval record {approval_id} has status {approval.status}, not APPROVED"
        )

    mapping = approval.path_mapping
    actor = approval.approver or "system"

    try:
        if approval.change_type == ChangeType.RENAME:
            _write_rename(db, approval, mapping)
        elif approval.change_type == ChangeType.PROMOTE:
            _write_promote(approval, mapping)
        elif mapping.is_promoted:
            _write_section_level(approval, mapping, page_id=mapping.page_id)
        elif mapping.parent_mapping_id is None:
            _write_page_level(approval, mapping)
        else:
            _write_section_level(approval, mapping, page_id=resolve_content_page_id(mapping))

        mapping.sync_status = SyncStatus.SYNCED
        _update_promotable_flag(approval, mapping)
        db.add(AuditLog(approval_record_id=approval.id, action=AuditAction.WRITE_SUCCEEDED, actor=actor))
    except Exception:
        mapping.sync_status = SyncStatus.FAILED
        db.add(AuditLog(approval_record_id=approval.id, action=AuditAction.WRITE_FAILED, actor=actor))
        db.flush()
        raise

    db.flush()


def _update_promotable_flag(approval: ApprovalRecord, mapping: PathMapping) -> None:
    """Recomputed after every successful section-level write, not just once --
    content shrinks as often as it grows (a big file gets trimmed, a section
    gets refactored down), so this should track the *current* state, not
    latch permanently true. Only meaningful for a not-yet-promoted section;
    a batch/page-level mapping is already its own page, and an already-
    promoted one doesn't need the signal anymore."""
    if mapping.parent_mapping_id is None or mapping.is_promoted:
        return
    if approval.change_type not in (ChangeType.CREATE, ChangeType.CONTENT_EDIT):
        return
    mapping.is_promotable = len(approval.proposed_content or "") > PROMOTION_CONTENT_LENGTH_THRESHOLD


def _resolve_batch_parent_page_id(mapping: PathMapping) -> str:
    """Where a batch/page-level mapping's Confluence page should be nested:
    its structural parent batch's page (e.g. "backend/lib" under "backend")
    if it has one and that parent's own page already exists, else the repo's
    root page -- covers top-level batches, and the case where a child batch
    is being created before its parent's page exists yet (self-heals via
    _self_heal_batch_parent once the parent does)."""
    if mapping.parent_batch_mapping_id is not None and mapping.parent_batch and mapping.parent_batch.page_id:
        return mapping.parent_batch.page_id
    return mapping.repo.root_page_id


def _self_heal_batch_parent(client, mapping: PathMapping) -> None:
    """If this batch page's real Confluence parent doesn't match where it
    should now nest -- a repo synced before batch-to-batch nesting existed,
    or a child page created under root while its own parent batch page
    didn't exist yet -- move it. Skipped for top-level batches (no
    parent_batch_mapping_id) and for a batch whose parent doesn't have a
    page yet, so it adds no cost for the common case."""
    if mapping.page_id is None or mapping.parent_batch_mapping_id is None:
        return
    parent_page_id = mapping.parent_batch.page_id if mapping.parent_batch else None
    if parent_page_id is None:
        return
    current = client.get_page(mapping.page_id)
    if current.get("parentId") != parent_page_id:
        client.move_page(mapping.page_id, parent_page_id)


def _write_page_level(approval: ApprovalRecord, mapping: PathMapping) -> None:
    """A batch-level (folder overview) page. Treated symmetrically with
    sections now: CREATE wraps the overview text in the same anchor-macro
    structure a section uses (mapping.section_anchor), so a later
    CONTENT_EDIT can replace just that block without touching any child
    sections appended into the same page body afterward (batch pages are
    shared -- the overview and its sections all live in one page).

    CONTENT_EDIT falls back to inserting a fresh anchored block if none is
    found (SectionNotFoundError): pages created before this anchor-wrap
    existed don't have one, so this self-heals them on first edit instead of
    failing forever."""
    client = get_confluence_client()
    _self_heal_batch_parent(client, mapping)

    if approval.change_type == ChangeType.CREATE:
        parent_id = _resolve_batch_parent_page_id(mapping)
        parent_page = client.get_page(parent_id)
        overview_html = markers.render_new_section(
            mapping.path, mapping.section_anchor, mapping.title, approval.proposed_content or ""
        )
        new_page = client.create_page(
            space_id=parent_page["spaceId"],
            parent_id=parent_id,
            title=mapping.title,
            html_body=overview_html,
        )
        mapping.page_id = new_page["id"]
    elif approval.change_type == ChangeType.CONTENT_EDIT:
        page = client.get_page(mapping.page_id, include_body=True)
        body = page["body"]["storage"]["value"]
        try:
            new_body = markers.replace_generated_block(
                body, mapping.section_anchor, approval.proposed_content or ""
            )
        except markers.SectionNotFoundError:
            overview_html = markers.render_new_section(
                mapping.path, mapping.section_anchor, mapping.title, approval.proposed_content or ""
            )
            new_body = markers.insert_section(body, overview_html)
        client.update_page(mapping.page_id, page["title"], new_body, page["version"]["number"])
    elif approval.change_type == ChangeType.DELETE:
        client.delete_page(mapping.page_id)
        mapping.page_id = None
    else:
        raise NotImplementedError(f"page-level {approval.change_type} not yet supported")


def _write_promote(approval: ApprovalRecord, mapping: PathMapping) -> None:
    """Cuts a section out of its parent batch page and gives it its own
    top-level Confluence page. Content doesn't change here -- proposed_content
    on the approval is exactly what was live in the parent page at
    promotion-request time (see propose_promotion); only where it physically
    lives changes. The new page reuses the same anchor-macro structure a
    normal section uses (mapping.section_anchor is untouched), so future
    content edits keep working via the is_promoted branch in write_approval --
    resolve_content_page_id then points at this mapping's own page_id instead
    of the old parent's."""
    if mapping.parent_mapping_id is None:
        raise ApprovalNotGrantedError(f"{mapping.path} has no parent batch to promote out of")
    parent = mapping.parent
    if parent.page_id is None:
        raise ApprovalNotGrantedError(
            f"parent page for {mapping.path} hasn't been created yet -- nothing to promote out of"
        )

    client = get_confluence_client()
    repo = mapping.repo
    root = client.get_page(repo.root_page_id)

    new_body = markers.render_new_section(
        mapping.path, mapping.section_anchor, mapping.title, approval.proposed_content or ""
    )
    new_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=repo.root_page_id,
        title=mapping.title,
        html_body=new_body,
    )

    parent_page = client.get_page(parent.page_id, include_body=True)
    trimmed_parent_body = markers.remove_section(
        parent_page["body"]["storage"]["value"], mapping.section_anchor
    )
    client.update_page(
        parent.page_id, parent_page["title"], trimmed_parent_body, parent_page["version"]["number"]
    )

    mapping.page_id = new_page["id"]
    mapping.is_promoted = True
    mapping.is_promotable = False  # already promoted -- the signal has nothing left to offer


def _write_rename(db: Session, approval: ApprovalRecord, mapping: PathMapping) -> None:
    """A rename/move -- content itself doesn't change (RENAME approvals
    snapshot current content at proposal time, same as PROMOTE), only the
    path and possibly which page it physically lives on. Three cases:

    - Already promoted: lives on its own page regardless of batch, so this
      is pure path bookkeeping -- nothing to move.
    - Same batch (the new path's level-2 ancestor is unchanged): the
      content stays on the same parent page -- pure bookkeeping too.
    - Cross-batch: the anchored content has to physically move from the old
      parent page's body to the new parent's -- same cut-and-insert shape as
      _write_promote, just landing on an existing batch page instead of a
      brand-new top-level one. The destination batch's own page has to
      already exist (its CREATE approved first), same dependency ordering
      a normal section create already requires.
    """
    new_path = approval.proposed_location

    if mapping.is_promoted:
        mapping.path = new_path
        return

    new_batch_key = _batch_key_for_path(new_path)
    old_parent = mapping.parent

    if old_parent is not None and old_parent.path == new_batch_key:
        mapping.path = new_path
        return

    new_batch_mapping = (
        db.query(PathMapping)
        .filter_by(repo_id=mapping.repo_id, path=new_batch_key, parent_mapping_id=None)
        .one_or_none()
    )
    if new_batch_mapping is None or new_batch_mapping.page_id is None:
        raise ApprovalNotGrantedError(
            f"destination batch page for {new_path!r} hasn't been created yet -- "
            f"approve its CREATE first"
        )

    client = get_confluence_client()

    if old_parent is not None and old_parent.page_id is not None:
        old_page = client.get_page(old_parent.page_id, include_body=True)
        trimmed_body = markers.remove_section(
            old_page["body"]["storage"]["value"], mapping.section_anchor
        )
        client.update_page(
            old_parent.page_id, old_page["title"], trimmed_body, old_page["version"]["number"]
        )

    new_page = client.get_page(new_batch_mapping.page_id, include_body=True)
    section_html = markers.render_new_section(
        new_path, mapping.section_anchor, mapping.title, approval.proposed_content or ""
    )
    inserted_body = markers.insert_section(new_page["body"]["storage"]["value"], section_html)
    client.update_page(
        new_batch_mapping.page_id, new_page["title"], inserted_body, new_page["version"]["number"]
    )

    mapping.path = new_path
    mapping.parent_mapping_id = new_batch_mapping.id


def _write_section_level(approval: ApprovalRecord, mapping: PathMapping, page_id: str | None) -> None:
    if page_id is None:
        raise ApprovalNotGrantedError(
            f"parent page for {mapping.path} hasn't been created yet -- "
            f"approve its CREATE first"
        )

    client = get_confluence_client()
    page = client.get_page(page_id, include_body=True)
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

    client.update_page(page_id, page["title"], new_body, version)
