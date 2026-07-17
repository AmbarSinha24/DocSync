from dataclasses import dataclass, field


@dataclass
class FileChange:
    path: str
    status: str  # "added" | "modified" | "removed" | "renamed"
    previous_path: str | None = None
    additions: int = 0
    deletions: int = 0
    patch: str | None = None  # populated only once full_patch detail is fetched
    size_bytes: int = 0  # populated for full-tree-walk entries (null baseline), where
    # there's no diff to measure additions/deletions from -- used as a LOC proxy instead


@dataclass
class Changeset:
    owner: str
    repo: str
    target_sha: str
    baseline_sha: str | None  # None means a full-tree walk (bootstrap/snapshot)
    changes: list[FileChange] = field(default_factory=list)
    commit_messages: list[str] = field(default_factory=list)  # oldest-first, empty for null baseline


@dataclass
class Batch:
    batch_key: str  # the level-2 folder path this batch covers (or shallower, if the path itself is shallower)
    changes: list[FileChange] = field(default_factory=list)


@dataclass
class Section:
    section_key: str  # immediate child (subfolder or leaf file) of the batch's folder page
    changes: list[FileChange] = field(default_factory=list)


class RepoTooLargeError(Exception):
    """Raised when a changeset's doc-worthy LOC exceeds the guardrail cap."""


class BaselineNotFoundError(Exception):
    """Raised when baseline_sha isn't reachable from target_sha within the search window
    (e.g. a force-push rewrote history). Phase 5 handles recovery; Phase 1 just surfaces it."""
