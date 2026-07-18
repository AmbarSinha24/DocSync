from sqlalchemy.orm import Session

from app.engine import markers
from app.engine.batcher import ROOT_BATCH_KEY, _parent_batch_key_for, batch_by_level2
from app.engine.classifier import classify_section
from app.engine.confluence_writer import resolve_content_page_id
from app.engine.manifest import resolve_mapping
from app.engine.models import Batch, Changeset, Section
from app.engine.sectioner import derive_section_path, partition_into_sections, section_full_path
from app.integrations.confluence import get_confluence_client
from app.integrations.llm import generate_section_content
from app.models import ApprovalRecord, ApprovalStatus, ChangeType, PathMapping


def _combined_patch(section: Section) -> str:
    parts = []
    for change in section.changes:
        header = f"--- {change.path} ({change.status})"
        if change.previous_path:
            header += f", renamed from {change.previous_path}"
        parts.append(header)
        if change.patch:
            parts.append(change.patch)
    return "\n".join(parts)


def _format_pr_context(commit_messages: list[str]) -> str | None:
    """Renders commit messages into the "why flagged" context stored on the
    approval record for the dashboard to display. None for a one-time
    snapshot (no commit history to show)."""
    if not commit_messages:
        return None
    return "\n".join(f"- {m}" for m in commit_messages)


def fetch_current_generated_content(mapping: PathMapping) -> str | None:
    """Reads the section's currently-live GENERATED block content from
    Confluence, for CONTENT_EDIT/DELETE cases where something already exists
    to compare against or show what's being removed. Returns None if the page
    it lives on doesn't exist yet (nothing to fetch) -- not an error, just
    means there's no "current" side of the diff. Uses resolve_content_page_id
    (shared with confluence_writer) so a promoted section's content is read
    from its own page, not its former parent's."""
    page_id = resolve_content_page_id(mapping)
    if page_id is None:
        return None

    client = get_confluence_client()
    page = client.get_page(page_id, include_body=True)
    body = page["body"]["storage"]["value"]
    return markers.get_generated_block(body, mapping.section_anchor)


def _has_pending_approval(db: Session, path_mapping_id: int) -> bool:
    return (
        db.query(ApprovalRecord)
        .filter_by(path_mapping_id=path_mapping_id, status=ApprovalStatus.PENDING)
        .count()
        > 0
    )


def _rename_candidate(db: Session, repo_id: int, new_path: str, section: Section) -> PathMapping | None:
    """If every change in this section is a clean rename (status="renamed"
    with a previous_path) and all of them resolve, via derive_section_path,
    back to the *same* old section path, and a PathMapping already exists
    there, returns it -- this section is a candidate to be recognized as
    that existing mapping relocated, rather than registered brand new.

    Doesn't check which batch the candidate's mapping currently belongs to
    -- that same-batch check happens where the real (already-resolved)
    batch mapping is available, in build_approval_records.
    """
    if db.query(PathMapping).filter_by(repo_id=repo_id, path=new_path).one_or_none() is not None:
        return None  # already a known path -- a normal edit, not a rename target
    if not section.changes or not all(
        c.status == "renamed" and c.previous_path for c in section.changes
    ):
        return None
    old_paths = {derive_section_path(c.previous_path) for c in section.changes}
    if len(old_paths) != 1:
        return None
    return db.query(PathMapping).filter_by(repo_id=repo_id, path=old_paths.pop()).one_or_none()


def _ensure_batch_page(
    db: Session, repo_id: int, batch: Batch, changeset: Changeset
) -> tuple[PathMapping, ApprovalRecord | None]:
    """Resolves the batch's own PathMapping (the folder-level overview page)
    and proposes whatever it needs next: CREATE if it doesn't exist yet,
    CONTENT_EDIT to refresh the overview if it does and this sync touched
    real files under it, or DELETE if every file that used to be under it
    was just removed -- symmetric with how sections are classified. Skips
    entirely if there's already a pending approval for it (a batch whose
    page was already approved+written, or already has a pending proposal,
    doesn't need another one stacked on top).

    If this batch's key has a parent key (e.g. "backend/lib" -> "backend"),
    looks it up directly rather than inventing it: either it was already
    resolved earlier in this same pass (batcher.batch_by_level2 sorts
    parents before children, and resolve_mapping flushes, so it's visible to
    this query), or it already exists as a PathMapping from a prior sync.
    If neither, the parent key was never independently real (no file has
    ever lived directly under it), so this batch stays top-level -- nothing
    here invents a folder-overview page that wouldn't otherwise exist. Also
    backfills parent_batch_mapping_id onto an already-existing mapping that
    predates this linkage (a repo synced before nesting was supported) --
    confluence_writer self-heals the actual Confluence page parent to match
    on the next write.
    """
    parent_batch_key = _parent_batch_key_for(batch.batch_key)
    parent_mapping = (
        db.query(PathMapping).filter_by(repo_id=repo_id, path=parent_batch_key).one_or_none()
        if parent_batch_key
        else None
    )

    mapping = resolve_mapping(
        db, repo_id, batch.batch_key, parent_path=None, sibling_paths=[],
        parent_batch_mapping_id=parent_mapping.id if parent_mapping else None,
    )
    if parent_mapping is not None and mapping.parent_batch_mapping_id is None:
        mapping.parent_batch_mapping_id = parent_mapping.id

    if _has_pending_approval(db, mapping.id):
        return mapping, None

    if mapping.page_id is None:
        change_type = ChangeType.CREATE
    elif batch.changes and all(c.status == "removed" for c in batch.changes):
        change_type = ChangeType.DELETE
    else:
        change_type = ChangeType.CONTENT_EDIT

    current_content = (
        fetch_current_generated_content(mapping)
        if change_type in (ChangeType.CONTENT_EDIT, ChangeType.DELETE)
        else None
    )

    diff_patch = _combined_patch(Section(section_key="", changes=batch.changes))
    if change_type == ChangeType.DELETE:
        content = None
    else:
        content = generate_section_content(
            path=batch.batch_key,
            diff_patch=diff_patch,
            commit_messages=changeset.commit_messages,
            commit_sha=changeset.target_sha,
            existing_content=current_content,
        )
    record = ApprovalRecord(
        path_mapping_id=mapping.id,
        change_type=change_type,
        proposed_content=content,
        current_content=current_content,
        diff_patch=diff_patch,
        commit_sha=changeset.target_sha,
        proposed_name=mapping.title if change_type == ChangeType.CREATE else None,
        proposed_location=batch.batch_key if change_type == ChangeType.CREATE else None,
        pr_context=_format_pr_context(changeset.commit_messages),
        status=ApprovalStatus.PENDING,
    )
    db.add(record)
    return mapping, record


def build_approval_records(db: Session, repo_id: int, changeset: Changeset) -> list[ApprovalRecord]:
    """Turns a filtered/guardrailed Changeset into pending ApprovalRecord rows.
    Two levels get resolved: the batch itself (the folder-level page, created
    once via its own CREATE approval), and each section within it (parented to
    the batch's mapping). DELETE records skip LLM content generation -- there's
    nothing to describe, just a removal to confirm -- but still fetch current
    content, so a reviewer can see exactly what's being removed.

    CONTENT_EDIT and DELETE both fetch the section's live GENERATED content
    from Confluence first: it's stored on the record as current_content (so
    the dashboard can show a real diff) and passed to the LLM as
    existing_content (so regeneration is informed by what's already there,
    not starting from scratch every time).

    RENAME is detected up front (a read-only pre-pass, before any batch page
    gets resolved for real) as a section whose changes are all clean renames
    resolving back to one existing PathMapping. Every file under a given
    subfolder collapses to the same section path regardless of depth (see
    sectioner.partition_into_sections), so a whole-folder rename already
    resolves to exactly one section-level RENAME here -- there's no separate
    multi-section grouping step needed for that case. Applies regardless of
    whether the old and new paths land in the same level-2 batch or
    different ones -- confluence_writer's _write_rename physically moves the
    anchored content between the two pages when they differ, mirroring the
    cut-and-insert pattern PROMOTE already uses.

    Individual section-level DELETE proposals are skipped for sections whose
    entire parent batch is also being deleted this sync (see _ensure_batch_page) --
    deleting the batch page already removes them, so a separate per-section
    confirmation would just be redundant noise. Promoted sections are the
    exception: they live on their own page, unaffected by their old batch
    page disappearing, so they still get their own DELETE proposal.
    """
    records: list[ApprovalRecord] = []
    batches = batch_by_level2(changeset)

    rename_candidates: dict[str, PathMapping] = {}
    for batch in batches:
        for section in partition_into_sections(batch):
            path = section_full_path(batch, section)
            source = _rename_candidate(db, repo_id, path, section)
            if source is not None:
                rename_candidates[path] = source

    for batch in batches:
        batch_mapping, batch_record = _ensure_batch_page(db, repo_id, batch, changeset)
        if batch_record is not None:
            records.append(batch_record)
        batch_being_deleted = batch_record is not None and batch_record.change_type == ChangeType.DELETE

        for section in partition_into_sections(batch):
            path = section_full_path(batch, section)

            rename_source = rename_candidates.get(path)
            if rename_source is not None:
                if _has_pending_approval(db, rename_source.id):
                    continue

                record = ApprovalRecord(
                    path_mapping_id=rename_source.id,
                    change_type=ChangeType.RENAME,
                    proposed_content=fetch_current_generated_content(rename_source),
                    diff_patch=_combined_patch(section),
                    commit_sha=changeset.target_sha,
                    proposed_name=rename_source.title,
                    proposed_location=path,
                    pr_context=_format_pr_context(changeset.commit_messages),
                    status=ApprovalStatus.PENDING,
                )
                db.add(record)
                records.append(record)
                continue

            change_type = classify_section(db, repo_id, path, section)

            parent_path = batch.batch_key if batch.batch_key != ROOT_BATCH_KEY else None
            mapping = resolve_mapping(
                db, repo_id, path, parent_path, sibling_paths=[],
                parent_mapping_id=batch_mapping.id,
            )

            if batch_being_deleted and change_type == ChangeType.DELETE and not mapping.is_promoted:
                continue

            if _has_pending_approval(db, mapping.id):
                continue

            current_content = (
                fetch_current_generated_content(mapping)
                if change_type in (ChangeType.CONTENT_EDIT, ChangeType.DELETE)
                else None
            )

            diff_patch = _combined_patch(section)
            if change_type == ChangeType.DELETE:
                content = None
            else:
                content = generate_section_content(
                    path=path,
                    diff_patch=diff_patch,
                    commit_messages=changeset.commit_messages,
                    commit_sha=changeset.target_sha,
                    existing_content=current_content,
                )

            record = ApprovalRecord(
                path_mapping_id=mapping.id,
                change_type=change_type,
                proposed_content=content,
                current_content=current_content,
                diff_patch=diff_patch,
                commit_sha=changeset.target_sha,
                proposed_name=mapping.title if change_type == ChangeType.CREATE else None,
                proposed_location=path if change_type == ChangeType.CREATE else None,
                pr_context=_format_pr_context(changeset.commit_messages),
                status=ApprovalStatus.PENDING,
            )
            db.add(record)
            records.append(record)

    db.flush()
    return records
