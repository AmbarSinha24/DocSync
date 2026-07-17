from sqlalchemy.orm import Session

from app.models import Repo, RepoSourceType


def get_or_create_repo(db: Session, owner: str, repo_name: str) -> Repo:
    """Looks up the Repo row for owner/repo_name. If none exists yet, this is the
    repo's first-ever sync -- creates the row with last_synced_sha=None, which
    naturally produces a null baseline (the same code path bootstrap/snapshot mode
    uses), rather than needing separate first-sync logic."""
    full_name = f"{owner}/{repo_name}"
    repo = db.query(Repo).filter_by(name=full_name).one_or_none()
    if repo is None:
        repo = Repo(name=full_name, source_type=RepoSourceType.GITHUB_APP)
        db.add(repo)
        db.flush()
    return repo


def resolve_baseline_sha(db: Session, owner: str, repo_name: str) -> tuple[Repo, str | None]:
    """Returns (repo, baseline_sha). baseline_sha is our own persisted
    last_synced_sha -- never the webhook's own `before` field -- so a failed sync
    doesn't silently get skipped on the next push. None means first-ever sync."""
    repo = get_or_create_repo(db, owner, repo_name)
    return repo, repo.last_synced_sha
