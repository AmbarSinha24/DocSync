from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.write_dispatcher import write_approved_records
from app.integrations.llm import generate_section_content, propose_name_and_location
from app.models import ApprovalRecord, ApprovalStatus, AuditAction, AuditLog, ChangeType

router = APIRouter()


class ActionRequest(BaseModel):
    actor: str = "unknown"


class EditRequest(BaseModel):
    actor: str = "unknown"
    proposed_name: str | None = None
    proposed_content: str | None = None


class RegenerateRequest(BaseModel):
    actor: str = "unknown"
    feedback: str | None = None


def _serialize(record: ApprovalRecord) -> dict:
    return {
        "id": record.id,
        "path": record.path_mapping.path,
        "change_type": record.change_type.value,
        "proposed_name": record.proposed_name,
        "proposed_content_preview": (record.proposed_content or "")[:300],
        "pr_context": record.pr_context,
        "status": record.status.value,
        "created_at": record.created_at.isoformat(),
    }


def _parse_pr_context(pr_context: str | None) -> list[str]:
    if not pr_context:
        return []
    return [line[2:] if line.startswith("- ") else line for line in pr_context.split("\n")]


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
    result["current_content"] = record.current_content
    return result


@router.patch("/approvals/{approval_id}")
def edit_approval(approval_id: int, body: EditRequest, db: Session = Depends(get_db)):
    """Inline edit before approving. Scoped to name and content -- editing
    proposed_location would mean renaming the underlying PathMapping's path,
    which cascades into parent linkage and hierarchy; out of scope here,
    left read-only for now rather than half-implemented."""
    record = _get_pending_or_404(db, approval_id)

    if body.proposed_name is not None:
        record.proposed_name = body.proposed_name
    if body.proposed_content is not None:
        record.proposed_content = body.proposed_content

    db.add(AuditLog(approval_record_id=record.id, action=AuditAction.EDITED, actor=body.actor))
    db.commit()

    result = _serialize(record)
    result["proposed_content"] = record.proposed_content
    return result


@router.post("/approvals/{approval_id}/regenerate")
def regenerate(approval_id: int, body: RegenerateRequest, db: Session = Depends(get_db)):
    """Re-runs LLM generation for a pending proposal, optionally steered by
    human feedback text -- the "regenerate" button for a rejected/unsatisfying
    proposal. Stays PENDING; this refreshes the proposal, it isn't itself an
    approve/reject decision."""
    record = _get_pending_or_404(db, approval_id)
    mapping = record.path_mapping

    if record.change_type == ChangeType.DELETE:
        raise HTTPException(
            status_code=400, detail="DELETE records have no generated content to regenerate"
        )
    if not record.diff_patch or not record.commit_sha:
        raise HTTPException(
            status_code=422, detail="no stored diff/commit context to regenerate from"
        )

    record.proposed_content = generate_section_content(
        path=mapping.path,
        diff_patch=record.diff_patch,
        commit_messages=_parse_pr_context(record.pr_context),
        commit_sha=record.commit_sha,
        existing_content=record.current_content,
        human_feedback=body.feedback,
    )

    if record.change_type == ChangeType.CREATE:
        parent_path = mapping.parent.path if mapping.parent else None
        proposal = propose_name_and_location(
            mapping.path, parent_path, sibling_paths=[], human_feedback=body.feedback
        )
        record.proposed_name = proposal["title"]

    db.add(
        AuditLog(approval_record_id=record.id, action=AuditAction.REGENERATED, actor=body.actor)
    )
    db.commit()

    result = _serialize(record)
    result["proposed_content"] = record.proposed_content
    return result


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: int, body: ActionRequest, db: Session = Depends(get_db)):
    record = _get_pending_or_404(db, approval_id)

    # a human-edited proposed_name becomes the mapping's canonical title now,
    # since the writer reads mapping.title, not approval.proposed_name
    if record.change_type == ChangeType.CREATE and record.proposed_name:
        record.path_mapping.title = record.proposed_name

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
