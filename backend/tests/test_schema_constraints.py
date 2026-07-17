import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ApprovalRecord, ChangeType, PathMapping, Repo, RepoSourceType


def make_repo(db, name="octocat/hello-world"):
    repo = Repo(name=name, source_type=RepoSourceType.GITHUB_APP)
    db.add(repo)
    db.flush()
    return repo


def make_mapping(db, repo, path="src/services/auth"):
    mapping = PathMapping(repo_id=repo.id, path=path)
    db.add(mapping)
    db.flush()
    return mapping


def test_valid_insert_chain_succeeds(db):
    repo = make_repo(db)
    mapping = make_mapping(db, repo)
    approval = ApprovalRecord(path_mapping_id=mapping.id, change_type=ChangeType.CREATE)
    db.add(approval)
    db.flush()
    assert approval.id is not None


def test_approval_record_rejects_nonexistent_path_mapping(db):
    bad_approval = ApprovalRecord(path_mapping_id=999999, change_type=ChangeType.CREATE)
    db.add(bad_approval)
    with pytest.raises(IntegrityError):
        db.flush()


def test_path_mapping_rejects_nonexistent_repo(db):
    bad_mapping = PathMapping(repo_id=999999, path="src/whatever")
    db.add(bad_mapping)
    with pytest.raises(IntegrityError):
        db.flush()


def test_duplicate_path_within_same_repo_rejected(db):
    repo = make_repo(db)
    make_mapping(db, repo, path="src/services/auth")
    db.flush()

    duplicate = PathMapping(repo_id=repo.id, path="src/services/auth")
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()


def test_same_path_allowed_across_different_repos(db):
    repo_a = make_repo(db, name="org/repo-a")
    repo_b = make_repo(db, name="org/repo-b")
    make_mapping(db, repo_a, path="src/services/auth")
    make_mapping(db, repo_b, path="src/services/auth")
    db.flush()  # should not raise
