from sqlalchemy.orm import Session

from app.engine.models import Section
from app.models import ChangeType, PathMapping


def classify_section(db: Session, repo_id: int, section_path: str, section: Section) -> ChangeType:
    """Structural (create/delete) vs content_edit, based on whether a PathMapping
    already exists for this section and whether all its underlying file changes
    are removals. Read-only -- does not create or modify any mapping.

    Scope note: folder-level rename/move detection is a Phase 5 concern. A
    file-level rename *within* an already-known section (the section's own
    identity doesn't change) is treated as a content edit here, not a
    structural "rename" -- the rename just shows up in the regenerated content.
    "promote" isn't produced by this classifier at all; it's a separate,
    human-confirmed flow, not something a push automatically triggers.
    """
    existing = db.query(PathMapping).filter_by(repo_id=repo_id, path=section_path).one_or_none()

    if existing is None:
        return ChangeType.CREATE
    if all(change.status == "removed" for change in section.changes):
        return ChangeType.DELETE
    return ChangeType.CONTENT_EDIT
