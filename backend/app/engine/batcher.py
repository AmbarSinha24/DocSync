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


def batch_by_level2(changeset: Changeset) -> list[Batch]:
    grouped: dict[str, list] = {}
    for change in changeset.changes:
        key = _batch_key_for_path(change.path)
        grouped.setdefault(key, []).append(change)

    return [Batch(batch_key=key, changes=changes) for key, changes in grouped.items()]
