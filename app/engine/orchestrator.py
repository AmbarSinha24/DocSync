import logging

from app.db import SessionLocal
from app.engine.approval_builder import build_approval_records
from app.engine.core import generate_changeset
from app.engine.repo_state import resolve_baseline_sha

logger = logging.getLogger("docsync.orchestrator")

TARGET_BRANCH = "main"


async def process_push(owner: str, repo_name: str, target_sha: str) -> None:
    """Entry point for a validated push-to-main webhook. Resolves our own
    persisted baseline (never the webhook's `before` field), runs the engine,
    classifies each section, and queues pending ApprovalRecords. Nothing is
    written to Confluence here -- that only happens once a human approves
    (#25's writer enforces this at the function-signature level).
    """
    db = SessionLocal()
    try:
        repo, baseline_sha = resolve_baseline_sha(db, owner, repo_name)
        db.commit()

        try:
            changeset = await generate_changeset(owner, repo_name, target_sha, baseline_sha)
        except Exception:
            logger.exception(
                "Failed to generate changeset for %s/%s at %s", owner, repo_name, target_sha
            )
            raise

        records = build_approval_records(db, repo.id, changeset)
        db.commit()

        logger.info(
            "Processed push for %s/%s: baseline=%s target=%s changed_paths=%d approval_records=%d",
            owner, repo_name, baseline_sha, target_sha, len(changeset.changes), len(records),
        )
    finally:
        db.close()
