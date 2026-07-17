from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PathMapping, Repo

router = APIRouter()


def _serialize_repo(repo: Repo) -> dict:
    return {
        "id": repo.id,
        "name": repo.name,
        "source_type": repo.source_type.value,
        "last_synced_sha": repo.last_synced_sha,
        "root_page_id": repo.root_page_id,
        "created_at": repo.created_at.isoformat(),
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
