import asyncio
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.engine.approval_builder import build_approval_records
from app.engine.core import generate_changeset
from app.engine.models import BaselineNotFoundError, Changeset
from app.engine.recovery import RECOVERY_NOTE, append_missing_section_deletions
from app.engine.repo_state import resolve_baseline_sha
from app.models import Repo

logger = logging.getLogger("docsync.orchestrator")

# Per-repo locks so two concurrent syncs for the SAME repo (a rapid double
# push, a GitHub webhook retry, or a UI re-sync racing a webhook) serialize
# instead of both reading the same last_synced_sha before either writes it
# back. Deliberately an in-process asyncio.Lock, not a DB-level `FOR UPDATE`
# row lock: this codebase's DB session is synchronous (plain pymysql), so a
# blocking lock-wait inside an `async def` would stall the *entire* event
# loop -- every other request on this worker, not just the racing repo --
# for up to the MySQL lock-wait timeout, which is a worse failure mode than
# the race it would prevent. asyncio.Lock yields properly instead. This only
# guards against races within a single worker process; a multi-process
# deployment would need a DB- or Redis-backed lock instead.
_repo_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def get_repo_lock(owner: str, repo_name: str) -> asyncio.Lock:
    return _repo_locks[f"{owner}/{repo_name}"]


async def run_sync(
    db: Session,
    owner: str,
    repo_name: str,
    repo: Repo,
    target_sha: str,
    baseline_sha: str | None,
    changeset: Changeset | None = None,
) -> tuple[Changeset, list]:
    """Shared sync pipeline: (changeset if not already computed) -> build
    approval records -> advance last_synced_sha -> commit. Used by both the
    webhook-triggered push flow and the add-repo/re-sync flow -- same engine
    either way, only how target_sha/baseline_sha get resolved differs between
    callers.

    last_synced_sha only advances here, after the changeset was successfully
    computed -- a failed read never silently gets skipped on the next sync,
    per the original "previous synced commit, not previous commit" decision.
    It advances before human approval happens (approval is async and can lag
    for a long time), but that's fine: it only needs to answer "since when do
    we scope the next diff", not "has everything from this push been
    approved yet" -- those are independent concerns.

    If baseline_sha is set but no longer reachable (force-push/history
    rewrite), falls back to a full bootstrap re-walk against the current
    tree instead of failing the sync outright. That re-walk is reconciled
    against already-synced PathMappings by the normal classify_section
    logic -- existing docs come back as CONTENT_EDIT (human-reviewed,
    nothing overwritten automatically), genuinely new paths as CREATE -- and
    append_missing_section_deletions additionally proposes DELETE for
    already-synced sections no longer present anywhere in the tree, since a
    plain tree-walk has no "removed" status of its own to report that.
    """
    if changeset is None:
        try:
            changeset = await generate_changeset(owner, repo_name, target_sha, baseline_sha)
        except* BaselineNotFoundError:
            # BaselineNotFoundError is raised inside the MCP client's `async with`
            # block, so anyio's task-group machinery wraps it in an ExceptionGroup
            # on the way out -- a plain `except BaselineNotFoundError` wouldn't
            # match that wrapper, hence `except*` (PEP 654) to unwrap by type.
            logger.warning(
                "baseline %s not found for %s/%s within the search window -- "
                "falling back to a full bootstrap re-walk",
                baseline_sha, owner, repo_name,
            )
            changeset = await generate_changeset(owner, repo_name, target_sha, None)
            changeset.commit_messages = [RECOVERY_NOTE]
            append_missing_section_deletions(db, repo.id, changeset)

    records = build_approval_records(db, repo.id, changeset)
    repo.last_synced_sha = target_sha
    db.commit()

    logger.info(
        "Synced %s/%s: baseline=%s target=%s changed_paths=%d approval_records=%d",
        owner, repo_name, baseline_sha, target_sha, len(changeset.changes), len(records),
    )
    return changeset, records


async def process_push(owner: str, repo_name: str, target_sha: str) -> None:
    """Entry point for a validated push-to-main webhook. Resolves our own
    persisted baseline (never the webhook's `before` field), runs the engine,
    classifies each section, and queues pending ApprovalRecords. Nothing is
    written to Confluence here -- that only happens once a human approves
    (#25's writer enforces this at the function-signature level).

    Serialized per-repo via get_repo_lock -- see its module-level comment for
    why a rapid double push or a webhook racing a UI re-sync could otherwise
    corrupt last_synced_sha.
    """
    async with get_repo_lock(owner, repo_name):
        db = SessionLocal()
        try:
            repo, baseline_sha = resolve_baseline_sha(db, owner, repo_name)
            db.commit()

            try:
                await run_sync(db, owner, repo_name, repo, target_sha, baseline_sha)
            except Exception:
                logger.exception(
                    "Failed to sync %s/%s at %s", owner, repo_name, target_sha
                )
                raise
        finally:
            db.close()
