import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.engine.approval_builder import fetch_current_generated_content
from app.engine.core import generate_changeset
from app.engine.github_reader import resolve_default_branch, resolve_default_branch_head
from app.engine.github_url import InvalidGitHubUrlError, parse_github_url
from app.engine.models import RepoTooLargeError
from app.engine.orchestrator import evict_repo_lock, get_repo_lock, run_sync
from app.integrations.confluence import get_confluence_client
from app.models import (
    ApprovalRecord,
    ApprovalStatus,
    AuditLog,
    ChangeType,
    JobStatus,
    PathMapping,
    Repo,
    RepoSourceType,
    SyncJob,
    SyncStatus,
)

# How long a terminal (DONE/FAILED) SyncJob row is kept before an opportunistic
# sweep removes it. No cron allowed -- this piggybacks on every POST /repos
# call instead. Covers both ordinary completed jobs (also reachable via
# DELETE /repos, but only once a Repo exists) and jobs that failed before a
# Repo row was ever created (repo_id stays NULL forever, e.g. RepoTooLargeError
# in _run_add_repo_job) -- DELETE /repos/{id} only ever reaches rows whose
# repo_id matches a real repo, so a NULL-repo_id row is otherwise unreachable
# by any existing path.
SYNC_JOB_RETENTION = timedelta(hours=24)


def _cleanup_old_sync_jobs(db: Session) -> None:
    cutoff = datetime.now(timezone.utc) - SYNC_JOB_RETENTION
    db.query(SyncJob).filter(
        SyncJob.status.in_([JobStatus.DONE, JobStatus.FAILED]),
        SyncJob.updated_at < cutoff,
    ).delete(synchronize_session=False)

logger = logging.getLogger("docsync.repos")

router = APIRouter()


class AddRepoRequest(BaseModel):
    url: str


def _serialize_repo(repo: Repo) -> dict:
    return {
        "id": repo.id,
        "name": repo.name,
        "source_type": repo.source_type.value,
        "last_synced_sha": repo.last_synced_sha,
        "root_page_id": repo.root_page_id,
        "created_at": repo.created_at.isoformat(),
        "confluence_url": (
            f"{settings.confluence_base_url}/wiki/pages/viewpage.action?pageId={repo.root_page_id}"
            if repo.root_page_id
            else None
        ),
    }


@router.get("/repos")
def list_repos(db: Session = Depends(get_db)):
    repos = db.query(Repo).order_by(Repo.name).all()
    return [_serialize_repo(r) for r in repos]


def _serialize_node(mapping: PathMapping, children_by_parent: dict) -> dict:
    return {
        "id": mapping.id,
        "path": mapping.path,
        "title": mapping.title,
        "page_id": mapping.page_id,
        "sync_status": mapping.sync_status.value,
        "is_promoted": mapping.is_promoted,
        "is_promotable": mapping.is_promotable,
        "children": [
            _serialize_node(child, children_by_parent)
            for child in children_by_parent.get(mapping.id, [])
        ],
    }


@router.get("/repos/{repo_id}")
def get_repo(repo_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    return _serialize_repo(repo)


@router.get("/repos/{repo_id}/tree")
def get_repo_tree(repo_id: int, db: Session = Depends(get_db)):
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")

    mappings = db.query(PathMapping).filter_by(repo_id=repo_id).all()
    children_by_parent: dict[int | None, list[PathMapping]] = {}
    for m in mappings:
        children_by_parent.setdefault(m.parent_mapping_id, []).append(m)

    roots = children_by_parent.get(None, [])
    return {
        "repo": _serialize_repo(repo),
        "tree": [_serialize_node(m, children_by_parent) for m in roots],
    }


@router.delete("/repos/{repo_id}")
def delete_repo(repo_id: int, db: Session = Depends(get_db)):
    """Removes a repo entirely: every distinct Confluence page it owns (its
    root page, plus each batch/promoted page's own page_id -- section-level
    mappings share their parent's page per resolve_content_page_id, so they
    don't own a separate page to delete), then all DB rows in FK-safe order.

    Confluence deletes happen first and un-transacted from the DB cleanup:
    if any of them fail, nothing is removed from the DB either, so the repo
    stays visible and the operation is safe to retry rather than silently
    orphaning live Confluence pages with no record left to find them by.
    """
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo not found")
    full_name = repo.name  # captured before db.commit() expires the instance

    mappings = db.query(PathMapping).filter_by(repo_id=repo.id).all()

    page_ids = {repo.root_page_id} if repo.root_page_id else set()
    for m in mappings:
        if (m.parent_mapping_id is None or m.is_promoted) and m.page_id:
            page_ids.add(m.page_id)

    client = get_confluence_client()
    for page_id in page_ids:
        try:
            client.delete_page(page_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                continue  # already gone -- fine, that's the goal anyway
            logger.exception("failed to delete Confluence page %s for repo %s", page_id, repo.name)
            raise HTTPException(
                status_code=502,
                detail=f"failed to delete Confluence page {page_id} -- repo not removed, safe to retry",
            )

    mapping_ids = [m.id for m in mappings]

    db.query(SyncJob).filter_by(repo_id=repo.id).delete()

    if mapping_ids:
        approval_ids_subq = db.query(ApprovalRecord.id).filter(
            ApprovalRecord.path_mapping_id.in_(mapping_ids)
        )
        db.query(AuditLog).filter(AuditLog.approval_record_id.in_(approval_ids_subq)).delete(
            synchronize_session=False
        )
        db.query(ApprovalRecord).filter(ApprovalRecord.path_mapping_id.in_(mapping_ids)).delete(
            synchronize_session=False
        )

    for m in [m for m in mappings if m.parent_mapping_id is not None]:
        db.delete(m)
    db.flush()
    for m in [m for m in mappings if m.parent_mapping_id is None]:
        db.delete(m)
    db.flush()

    db.delete(repo)
    db.commit()

    evict_repo_lock(full_name)

    return {"deleted": True, "repo_id": repo_id}


def _serialize_job(job: SyncJob) -> dict:
    return {
        "id": job.id,
        "full_name": job.full_name,
        "status": job.status.value,
        "repo_id": job.repo_id,
        "pending_approvals": job.pending_approvals,
        "error_message": job.error_message,
    }


@router.post("/repos", status_code=202)
async def add_repo(body: AddRepoRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Unified add-or-resync: an unknown repo gets a one-time snapshot (LOC
    guardrail runs before any write happens, so a too-large repo leaves no
    orphaned Confluence page or DB row behind); an already-onboarded repo
    (enforced by the unique constraint on Repo.name) gets an incremental
    diff against its last synced SHA through the exact same pipeline.

    URL parsing and repo-existence are checked synchronously here so bad
    input fails fast with a clean 4xx -- everything past that (the tree walk,
    LLM naming, Confluence page creation) can take a while for a large repo,
    so it runs as a background task tracked via a SyncJob row instead of
    blocking the request. The frontend polls GET /repo-jobs/{id} for
    progress, which survives a page navigation since it's server-side state,
    not local component state.
    """
    try:
        owner, repo_name = parse_github_url(body.url)
    except InvalidGitHubUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        target_sha = await resolve_default_branch_head(owner, repo_name)
    except Exception:
        raise HTTPException(
            status_code=404,
            detail=f"{owner}/{repo_name} not found or inaccessible -- check the URL and that the repo is public",
        )

    full_name = f"{owner}/{repo_name}"

    _cleanup_old_sync_jobs(db)

    job = SyncJob(full_name=full_name, status=JobStatus.QUEUED)
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_run_add_repo_job, job.id, owner, repo_name, target_sha)
    return _serialize_job(job)


@router.get("/repo-jobs/{job_id}")
def get_repo_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _serialize_job(job)


async def _run_add_repo_job(job_id: int, owner: str, repo_name: str, target_sha: str) -> None:
    """Runs the actual add-or-resync pipeline as a background task, driven by
    the job created in add_repo. Opens its own DB session -- the request's
    session is closed by the time a background task runs -- matching the
    pattern process_push already uses for webhook-triggered syncs."""
    full_name = f"{owner}/{repo_name}"
    db = SessionLocal()
    try:
        job = db.get(SyncJob, job_id)
        job.status = JobStatus.PROCESSING
        db.commit()

        try:
            async with get_repo_lock(owner, repo_name):
                existing = db.query(Repo).filter_by(name=full_name).one_or_none()

                if existing is None:
                    changeset = await generate_changeset(owner, repo_name, target_sha, None)
                    default_branch = await resolve_default_branch(owner, repo_name)

                    client = get_confluence_client()
                    root = client.get_page(settings.confluence_root_page_id)
                    page = client.create_page(
                        space_id=root["spaceId"],
                        parent_id=settings.confluence_root_page_id,
                        title=full_name,
                        html_body=f"<p>Documentation for <code>{full_name}</code>.</p>",
                    )

                    repo = Repo(
                        name=full_name,
                        source_type=RepoSourceType.PUBLIC_SNAPSHOT,
                        root_page_id=page["id"],
                        default_branch=default_branch,
                    )
                    db.add(repo)
                    db.flush()

                    _, records = await run_sync(
                        db, owner, repo_name, repo, target_sha, None, changeset=changeset
                    )
                else:
                    repo = existing
                    _, records = await run_sync(
                        db, owner, repo_name, repo, target_sha, repo.last_synced_sha
                    )

            job.status = JobStatus.DONE
            job.repo_id = repo.id
            job.pending_approvals = len(records)
            db.commit()
        except RepoTooLargeError as e:
            db.rollback()
            job = db.get(SyncJob, job_id)
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            db.commit()
        except Exception:
            db.rollback()
            job = db.get(SyncJob, job_id)
            job.status = JobStatus.FAILED
            job.error_message = "unexpected error -- check server logs"
            db.commit()
            logger.exception("add-repo job %s failed for %s", job_id, full_name)
    finally:
        db.close()


@router.post("/path-mappings/{mapping_id}/promote")
def propose_promotion(mapping_id: int, db: Session = Depends(get_db)):
    """Human-confirmed promotion: cuts a section out of its parent batch page
    into its own top-level Confluence page. Never automatic -- is_promotable
    (see confluence_writer._update_promotable_flag) only ever surfaces the
    option in the UI; a human always has to explicitly request it here.
    Goes through the same ApprovalRecord + approve/reject/write pipeline as
    every other change, so it's reviewable and auditable through the
    existing dashboard -- only the actual page-split logic
    (confluence_writer._write_promote) is new.

    Deliberately doesn't require is_promotable to be true: that flag is a
    suggestion based on content size, not a hard gate -- a human may have
    good reason to promote something smaller (it's about to grow, or it's
    conceptually important enough to deserve its own page regardless).
    """
    mapping = db.get(PathMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="path mapping not found")
    if mapping.parent_mapping_id is None:
        raise HTTPException(
            status_code=400, detail="only sections can be promoted, not batch/page-level entries"
        )
    if mapping.is_promoted:
        raise HTTPException(status_code=409, detail="already promoted")
    if mapping.sync_status != SyncStatus.SYNCED:
        raise HTTPException(status_code=409, detail="mapping has no live content yet to promote")

    has_pending = (
        db.query(ApprovalRecord)
        .filter_by(path_mapping_id=mapping.id, status=ApprovalStatus.PENDING)
        .count()
        > 0
    )
    if has_pending:
        raise HTTPException(status_code=409, detail="already has a pending approval")

    current_content = fetch_current_generated_content(mapping)
    if not current_content:
        raise HTTPException(status_code=422, detail="nothing live to promote")

    record = ApprovalRecord(
        path_mapping_id=mapping.id,
        change_type=ChangeType.PROMOTE,
        proposed_content=current_content,
        current_content=current_content,
        proposed_name=mapping.title,
        proposed_location=mapping.path,
        pr_context="Human-initiated: promote this section to its own top-level page.",
        status=ApprovalStatus.PENDING,
    )
    db.add(record)
    db.commit()

    return {
        "id": record.id,
        "path": mapping.path,
        "change_type": record.change_type.value,
        "status": record.status.value,
    }
