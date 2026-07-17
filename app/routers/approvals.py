from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.write_dispatcher import write_approved_records
from app.models import ApprovalRecord, ApprovalStatus, AuditAction, AuditLog

router = APIRouter()


class ActionRequest(BaseModel):
    actor: str = "unknown"


def _serialize(record: ApprovalRecord) -> dict:
    return {
        "id": record.id,
        "path": record.path_mapping.path,
        "change_type": record.change_type.value,
        "proposed_name": record.proposed_name,
        "proposed_content_preview": (record.proposed_content or "")[:300],
        "status": record.status.value,
        "created_at": record.created_at.isoformat(),
    }


def _get_pending_or_404(db: Session, approval_id: int) -> ApprovalRecord:
    record = db.get(ApprovalRecord, approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="approval record not found")
    if record.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"record has status {record.status.value}, not pending"
        )
    return record


@router.get("/approvals")
def list_approvals(status: str = "pending", db: Session = Depends(get_db)):
    try:
        status_enum = ApprovalStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid status '{status}'")

    records = db.query(ApprovalRecord).filter(ApprovalRecord.status == status_enum).all()
    return [_serialize(r) for r in records]


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: int, db: Session = Depends(get_db)):
    record = db.get(ApprovalRecord, approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="approval record not found")
    result = _serialize(record)
    result["proposed_content"] = record.proposed_content
    return result


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: int, body: ActionRequest, db: Session = Depends(get_db)):
    record = _get_pending_or_404(db, approval_id)

    record.status = ApprovalStatus.APPROVED
    record.approver = body.actor
    record.resolved_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(approval_record_id=record.id, action=AuditAction.APPROVED, actor=body.actor)
    )
    db.commit()

    results = write_approved_records(db, [approval_id])
    return {"id": approval_id, "status": "approved", "write_result": results[approval_id]}


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: int, body: ActionRequest, db: Session = Depends(get_db)):
    record = _get_pending_or_404(db, approval_id)

    record.status = ApprovalStatus.REJECTED
    record.approver = body.actor
    record.resolved_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(approval_record_id=record.id, action=AuditAction.REJECTED, actor=body.actor)
    )
    db.commit()
    return {"id": approval_id, "status": "rejected"}
