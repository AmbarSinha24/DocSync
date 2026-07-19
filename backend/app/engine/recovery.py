from sqlalchemy.orm import Session

from app.engine.models import Changeset, FileChange
from app.models import PathMapping, SyncStatus

RECOVERY_NOTE = (
    "Baseline commit was no longer reachable from the pushed SHA (likely a "
    "force-push or history rewrite). This sync is a full re-walk of the "
    "current tree, reconciled against already-synced docs -- double check any "
    "DELETE proposals below against the repo directly before approving."
)


def append_missing_section_deletions(db: Session, repo_id: int, changeset: Changeset) -> None:
    """After a baseline-recovery bootstrap re-walk (see BaselineNotFoundError),
    a plain tree-listing has no "removed" concept -- it only reports what
    currently exists, so anything deleted by the force-push would otherwise go
    unnoticed. This finds already-synced section-level mappings whose path no
    longer matches any file in the current tree and appends a synthetic
    removed FileChange for each, so the normal batch/section/classify
    pipeline proposes a DELETE for them exactly as it would from a real diff.

    Only section-level mappings are considered -- batch/page-level delete
    isn't supported by confluence_writer yet (same scope limit noted in
    classify_section and _write_page_level).

    Excludes mappings whose removed_at is already set -- write_approval sets
    sync_status=SYNCED on *any* successful write including a DELETE, so a
    section already marked removed would otherwise get a second, redundant
    synthetic "removed" FileChange appended on every force-push recovery for
    content that's already gone.
    """
    current_paths = {c.path for c in changeset.changes}

    stale_mappings = (
        db.query(PathMapping)
        .filter_by(repo_id=repo_id, sync_status=SyncStatus.SYNCED)
        .filter(PathMapping.parent_mapping_id.isnot(None))
        .filter(PathMapping.removed_at.is_(None))
        .all()
    )
    for mapping in stale_mappings:
        still_present = any(
            p == mapping.path or p.startswith(mapping.path + "/") for p in current_paths
        )
        if not still_present:
            changeset.changes.append(FileChange(path=mapping.path, status="removed"))
