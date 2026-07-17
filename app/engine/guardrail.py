from app.engine.models import Changeset, RepoTooLargeError

LOC_CAP = 20_000
AVG_BYTES_PER_LINE = 40  # heuristic for estimating LOC from raw file size (bootstrap mode,
# where there's no diff to measure additions/deletions from)


def _estimated_loc(change) -> int:
    if change.additions or change.deletions:
        return change.additions + change.deletions
    if change.size_bytes:
        return max(1, change.size_bytes // AVG_BYTES_PER_LINE)
    return 0


def total_loc(changeset: Changeset) -> int:
    return sum(_estimated_loc(c) for c in changeset.changes)


def enforce_loc_guardrail(changeset: Changeset, cap: int = LOC_CAP) -> None:
    """Hard-blocks before any LLM call is made. Raises RepoTooLargeError if the
    changeset's estimated LOC exceeds the cap. Applies uniformly to both the
    null-baseline (bootstrap/snapshot) and incremental-diff cases -- callers
    should run this after doc_worthy_filter, so excluded noise never counts."""
    loc = total_loc(changeset)
    if loc > cap:
        raise RepoTooLargeError(
            f"changeset for {changeset.owner}/{changeset.repo} is ~{loc} estimated LOC, "
            f"exceeding the {cap} cap"
        )
