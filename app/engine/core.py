from app.engine.models import Changeset

# Filled in by tasks #11-16:
# - app.engine.github_reader: read_changeset(owner, repo, target_sha, baseline_sha) -> Changeset
# - app.engine.filter: doc_worthy_filter(changeset) -> Changeset (noise paths dropped)
# - app.engine.guardrail: enforce_loc_guardrail(changeset) -> None (raises RepoTooLargeError)
# - app.engine.batcher: batch_by_level2(changeset) -> list[Batch]
# - app.engine.manifest: resolve_mapping(db, repo_id, path) -> PathMapping (LLM-names on first sighting)


async def generate_changeset(owner: str, repo: str, target_sha: str, baseline_sha: str | None) -> Changeset:
    """The unified engine entry point: (repo_source, target_sha, baseline_sha_or_null) -> changeset.

    baseline_sha=None means a full-tree walk (bootstrap sync or a one-time public-repo
    snapshot) -- both callers into this engine (push-triggered sync and the "add public
    repo" UI flow) go through this same function, differing only in what they pass here.

    Pipeline order: read -> filter -> guardrail -> batch. The guardrail runs before any
    LLM call is made, on the *filtered* set (noise paths shouldn't count against the cap).
    """
    from app.engine.filter import doc_worthy_filter
    from app.engine.github_reader import read_changeset
    from app.engine.guardrail import enforce_loc_guardrail

    changeset = await read_changeset(owner, repo, target_sha, baseline_sha)
    changeset = doc_worthy_filter(changeset)
    enforce_loc_guardrail(changeset)
    return changeset
