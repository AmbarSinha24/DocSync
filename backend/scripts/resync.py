"""Manually re-syncs an already-onboarded repo, for recovery when a push
webhook was missed (delivery failure, downtime, etc.) and last_synced_sha has
fallen behind the repo's real current state. Goes through the exact same
run_sync pipeline as the webhook and add-repo flows -- same incremental diff
against our own persisted last_synced_sha, same force-push/history-rewrite
fallback (#51), same same-batch rename detection (#52), same approval gate.

This is for an already-known repo only. To onboard a brand-new repo, use the
Add Repo UI (POST /repos) instead -- that path also creates the repo's root
Confluence page, which this script deliberately doesn't do.

Usage:
    python scripts/resync.py <owner>/<repo>
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `app` resolves regardless of cwd

from app.db import SessionLocal
from app.engine.github_reader import resolve_default_branch_head
from app.engine.models import RepoTooLargeError
from app.engine.orchestrator import run_sync
from app.models import Repo


async def main(full_name: str) -> int:
    if "/" not in full_name:
        print(f"error: expected '<owner>/<repo>', got {full_name!r}", file=sys.stderr)
        return 1
    owner, repo_name = full_name.split("/", 1)

    db = SessionLocal()
    try:
        repo = db.query(Repo).filter_by(name=full_name).one_or_none()
        if repo is None:
            print(
                f"error: {full_name} isn't onboarded yet -- use the Add Repo UI "
                f"(POST /repos) for a first-time sync, not this script",
                file=sys.stderr,
            )
            return 1

        try:
            target_sha = await resolve_default_branch_head(owner, repo_name)
        except Exception as e:
            print(f"error: couldn't resolve {full_name}'s default branch HEAD: {e}", file=sys.stderr)
            return 1

        print(f"resyncing {full_name}: last_synced_sha={repo.last_synced_sha} -> target={target_sha}")

        try:
            changeset, records = await run_sync(
                db, owner, repo_name, repo, target_sha, repo.last_synced_sha
            )
        except RepoTooLargeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        print(
            f"done: baseline={changeset.baseline_sha} target={changeset.target_sha} "
            f"changed_paths={len(changeset.changes)} approval_records={len(records)}"
        )
        for r in records:
            print(f"  APPROVAL_ID={r.id} path={r.path_mapping.path} type={r.change_type.value}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manually resync an already-onboarded repo.")
    parser.add_argument("repo", help="owner/repo, e.g. AmbarSinha24/docsync-fixture")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.repo)))
