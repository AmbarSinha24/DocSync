import json

from app.engine.models import BaselineNotFoundError, Changeset, FileChange
from app.integrations.github_mcp import github_mcp_session

MAX_PAGES_SEARCHED_FOR_BASELINE = 10
COMMITS_PER_PAGE = 100


async def _call_tool_json(session, name: str, arguments: dict):
    result = await session.call_tool(name, arguments)
    text = "".join(block.text for block in result.content if hasattr(block, "text"))
    return json.loads(text)


async def _find_commit_range(session, owner: str, repo: str, target_sha: str, baseline_sha: str) -> list[str]:
    """Returns commit SHAs strictly between baseline_sha (exclusive) and target_sha
    (inclusive), newest-first. Raises BaselineNotFoundError if baseline_sha isn't
    reachable within the search window (e.g. a force-pushed/rewritten history)."""
    if target_sha == baseline_sha:
        return []

    collected: list[str] = []
    for page in range(1, MAX_PAGES_SEARCHED_FOR_BASELINE + 1):
        commits = await _call_tool_json(
            session,
            "list_commits",
            {"owner": owner, "repo": repo, "sha": target_sha, "perPage": COMMITS_PER_PAGE, "page": page},
        )
        if not commits:
            break
        for commit in commits:
            if commit["sha"] == baseline_sha:
                return collected
            collected.append(commit["sha"])

    raise BaselineNotFoundError(
        f"baseline_sha {baseline_sha} not found within {MAX_PAGES_SEARCHED_FOR_BASELINE} "
        f"pages of history from {target_sha} (possible force-push/history rewrite)"
    )


def _aggregate_files(commits_files: list[list[dict]]) -> list[FileChange]:
    """Aggregates per-commit file lists (oldest-first) into a single net changeset
    relative to baseline. Handles the common add/modify/remove/rename cases within
    a small commit range; pathological multi-hop rename chains are a Phase 5 concern."""
    by_path: dict[str, FileChange] = {}

    for files in commits_files:
        for f in files:
            path = f["filename"]
            status = f["status"]

            if status == "renamed":
                previous_path = f.get("previous_filename")
                existing = by_path.pop(previous_path, None) if previous_path else None
                carried_previous = existing.previous_path if existing else previous_path
                by_path[path] = FileChange(
                    path=path,
                    status="renamed",
                    previous_path=carried_previous,
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch"),
                )
            elif status == "added":
                by_path[path] = FileChange(
                    path=path,
                    status="added",
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch"),
                )
            elif status == "removed":
                if path in by_path and by_path[path].status == "added":
                    # added then removed within the same range -> net no-op
                    del by_path[path]
                else:
                    by_path[path] = FileChange(path=path, status="removed")
            else:  # "modified" (or any other in-place status)
                existing = by_path.get(path)
                net_status = existing.status if existing and existing.status == "added" else "modified"
                by_path[path] = FileChange(
                    path=path,
                    status=net_status,
                    previous_path=existing.previous_path if existing else None,
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch"),
                )

    return list(by_path.values())


async def _read_incremental_changeset(
    session, owner: str, repo: str, target_sha: str, baseline_sha: str
) -> tuple[list[FileChange], list[str]]:
    commit_shas = await _find_commit_range(session, owner, repo, target_sha, baseline_sha)
    if not commit_shas:
        return [], []

    # oldest-first, so aggregation applies changes in the order they actually happened
    commit_shas.reverse()

    commits_files = []
    commit_messages = []
    for sha in commit_shas:
        commit = await _call_tool_json(
            session, "get_commit", {"owner": owner, "repo": repo, "sha": sha, "detail": "full_patch"}
        )
        commits_files.append(commit.get("files", []))
        message = commit.get("commit", {}).get("message")
        if message:
            commit_messages.append(message)

    return _aggregate_files(commits_files), commit_messages


async def _walk_tree(session, owner: str, repo: str, ref: str, path: str = "/") -> list[FileChange]:
    entries = await _call_tool_json(session, "get_file_contents", {"owner": owner, "repo": repo, "path": path, "ref": ref})
    if isinstance(entries, dict):  # a single file was requested, not a directory
        entries = [entries]

    changes: list[FileChange] = []
    for entry in entries:
        if entry["type"] == "dir":
            changes.extend(await _walk_tree(session, owner, repo, ref, entry["path"]))
        else:
            changes.append(
                FileChange(path=entry["path"], status="added", size_bytes=entry.get("size", 0))
            )
    return changes


async def read_changeset(owner: str, repo: str, target_sha: str, baseline_sha: str | None) -> Changeset:
    async with github_mcp_session() as session:
        if baseline_sha is None:
            changes = await _walk_tree(session, owner, repo, target_sha)
            commit_messages: list[str] = []
        else:
            changes, commit_messages = await _read_incremental_changeset(
                session, owner, repo, target_sha, baseline_sha
            )

    return Changeset(
        owner=owner,
        repo=repo,
        target_sha=target_sha,
        baseline_sha=baseline_sha,
        changes=changes,
        commit_messages=commit_messages,
    )
