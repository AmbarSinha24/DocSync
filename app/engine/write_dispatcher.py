import logging

from sqlalchemy.orm import Session

from app.engine.confluence_writer import write_approval
from app.models import ApprovalRecord, ApprovalStatus, PathMapping, SyncStatus

logger = logging.getLogger("docsync.writer")


def write_approved_records(db: Session, approval_ids: list[int]) -> dict[int, str]:
    """Writes each approved record independently -- one failure doesn't stop
    the rest, and each mapping's own sync_status (already set inside
    write_approval) reflects exactly what happened to it. Returns
    {approval_id: "synced"|"failed"} for the caller to inspect.
    """
    results: dict[int, str] = {}
    for approval_id in approval_ids:
        try:
            write_approval(db, approval_id)
            db.commit()
            results[approval_id] = "synced"
        except Exception:
            # write_approval already set sync_status=FAILED and flushed it --
            # commit that marker rather than rolling it back. A plain rollback()
            # here would silently discard the very failure record we want kept.
            db.commit()
            logger.exception("Failed to write approval %d", approval_id)
            results[approval_id] = "failed"
    return results


def retry_failed(db: Session, repo_id: int) -> dict[int, str]:
    """Re-attempts only entries whose PathMapping is currently sync_status=FAILED.
    Untouched entries (SYNCED or PENDING) are left alone -- this only reprocesses
    what actually failed, not the whole repo."""
    failed_mappings = (
        db.query(PathMapping).filter_by(repo_id=repo_id, sync_status=SyncStatus.FAILED).all()
    )

    approval_ids = []
    for mapping in failed_mappings:
        latest_approved = (
            db.query(ApprovalRecord)
            .filter_by(path_mapping_id=mapping.id, status=ApprovalStatus.APPROVED)
            .order_by(ApprovalRecord.created_at.desc())
            .first()
        )
        if latest_approved:
            approval_ids.append(latest_approved.id)

    return write_approved_records(db, approval_ids)
