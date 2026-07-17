from sqlalchemy.orm import Session

from app.engine.batcher import ROOT_BATCH_KEY, batch_by_level2
from app.engine.classifier import classify_section
from app.engine.manifest import resolve_mapping
from app.engine.models import Batch, Changeset, Section
from app.engine.sectioner import partition_into_sections, section_full_path
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


def _has_pending_approval(db: Session, path_mapping_id: int) -> bool:
    return (
        db.query(ApprovalRecord)
        .filter_by(path_mapping_id=path_mapping_id, status=ApprovalStatus.PENDING)
        .count()
        > 0
    )


def _ensure_batch_page(
    db: Session, repo_id: int, batch: Batch, changeset: Changeset
) -> tuple[PathMapping, ApprovalRecord | None]:
    """Resolves the batch's own PathMapping (the folder-level page itself).
    Only produces a new ApprovalRecord if the page doesn't exist yet (no
    page_id) and there isn't already a pending CREATE for it -- a batch whose
    page was already approved+written, or already has a pending proposal,
    doesn't need another one just because more of its sections changed.
    """
    mapping = resolve_mapping(db, repo_id, batch.batch_key, parent_path=None, sibling_paths=[])

    if mapping.page_id is not None or _has_pending_approval(db, mapping.id):
        return mapping, None

    content = generate_section_content(
        path=batch.batch_key,
        diff_patch=_combined_patch(Section(section_key="", changes=batch.changes)),
        commit_messages=changeset.commit_messages,
        commit_sha=changeset.target_sha,
        existing_content=None,
    )
    record = ApprovalRecord(
        path_mapping_id=mapping.id,
        change_type=ChangeType.CREATE,
        proposed_content=content,
        proposed_name=mapping.title,
        proposed_location=batch.batch_key,
        status=ApprovalStatus.PENDING,
    )
    db.add(record)
    return mapping, record


def build_approval_records(db: Session, repo_id: int, changeset: Changeset) -> list[ApprovalRecord]:
    """Turns a filtered/guardrailed Changeset into pending ApprovalRecord rows.
    Two levels get resolved: the batch itself (the folder-level page, created
    once via its own CREATE approval), and each section within it (parented to
    the batch's mapping). DELETE records skip LLM content generation -- there's
    nothing to describe, just a removal to confirm.

    Known simplification: existing_content is always None here, so every
    regeneration starts from scratch rather than being informed by the
    section's current Confluence content. Existing-content awareness needs
    the Confluence writer's page-parsing logic to read the current GENERATED
    block first -- natural to build together with the writer rather than
    duplicating that parsing here.
    """
    records: list[ApprovalRecord] = []

    for batch in batch_by_level2(changeset):
        batch_mapping, batch_record = _ensure_batch_page(db, repo_id, batch, changeset)
        if batch_record is not None:
            records.append(batch_record)

        for section in partition_into_sections(batch):
            path = section_full_path(batch, section)
            change_type = classify_section(db, repo_id, path, section)

            parent_path = batch.batch_key if batch.batch_key != ROOT_BATCH_KEY else None
            mapping = resolve_mapping(
                db, repo_id, path, parent_path, sibling_paths=[],
                parent_mapping_id=batch_mapping.id,
            )

            if _has_pending_approval(db, mapping.id):
                continue

            if change_type == ChangeType.DELETE:
                content = None
            else:
                content = generate_section_content(
                    path=path,
                    diff_patch=_combined_patch(section),
                    commit_messages=changeset.commit_messages,
                    commit_sha=changeset.target_sha,
                    existing_content=None,
                )

            record = ApprovalRecord(
                path_mapping_id=mapping.id,
                change_type=change_type,
                proposed_content=content,
                proposed_name=mapping.title if change_type == ChangeType.CREATE else None,
                proposed_location=path if change_type == ChangeType.CREATE else None,
                status=ApprovalStatus.PENDING,
            )
            db.add(record)
            records.append(record)

    db.flush()
    return records
