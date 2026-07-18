from app.engine.models import Batch, Changeset

ROOT_BATCH_KEY = "(root)"


def _batch_key_for_path(path: str) -> str:
    """Level 0 is root. A path's batch key is its level-2 ancestor folder --
    e.g. src/services/auth/login.py -> "src/services". Paths shallower than
    level 2 batch at whatever level they actually live at: a file directly
    under a level-1 folder batches by that folder; a root-level file gets
    its own root-level batch."""
    dir_parts = path.split("/")[:-1]  # directory components, excluding the filename
    if not dir_parts:
        return ROOT_BATCH_KEY
    return "/".join(dir_parts[:2])


def _parent_batch_key_for(batch_key: str) -> str | None:
    """The batch key that should be this batch's structural Confluence
    parent -- e.g. "backend/lib" -> "backend". None for a top-level batch
    (ROOT_BATCH_KEY, or a single folder segment), whose Confluence parent is
    just the repo's root page, not another batch. Batch keys are at most two
    segments deep (level-2 batching), so this only ever needs to strip one
    level -- no recursion required."""
    if batch_key == ROOT_BATCH_KEY:
        return None
    segments = batch_key.split("/")
    if len(segments) == 1:
        return None
    return segments[0]


def batch_by_level2(changeset: Changeset) -> list[Batch]:
    """Only ever batches keys that actually have real changes under them --
    a level-2 key like "src/services" with no sibling "src" batch (no file
    ever lives directly in src/) legitimately stays a top-level batch, same
    as always. Nesting (see _ensure_batch_page) only kicks in when a batch's
    parent key is *also* independently real -- either it has its own changes
    in this same changeset, or it already exists as a PathMapping from a
    prior sync. Nothing here invents a folder-overview page that wouldn't
    otherwise exist."""
    grouped: dict[str, list] = {}
    for change in changeset.changes:
        key = _batch_key_for_path(change.path)
        grouped.setdefault(key, []).append(change)

    # When a batch and its parent both land in the same changeset, the
    # parent must be resolved first so the child can link to it in the same
    # pass -- sort by segment count (fewer segments = shallower = first).
    ordered_keys = sorted(grouped.keys(), key=lambda k: 0 if k == ROOT_BATCH_KEY else k.count("/"))

    return [Batch(batch_key=key, changes=grouped[key]) for key in ordered_keys]
