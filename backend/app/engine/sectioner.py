from app.engine.batcher import ROOT_BATCH_KEY, _batch_key_for_path
from app.engine.models import Batch, Section


def _section_key(batch_key: str, path: str) -> str:
    """The immediate child of the batch's folder -- a subfolder name or a leaf
    filename -- becomes the section key. E.g. for batch_key "src/services" and
    path "src/services/auth/deep/thing.py", the section key is "auth" (everything
    under it lives in that one section until it's promoted to its own page)."""
    if batch_key == ROOT_BATCH_KEY:
        relative = path
    else:
        prefix = batch_key + "/"
        relative = path[len(prefix):] if path.startswith(prefix) else path
    return relative.split("/")[0]


def section_full_path(batch: Batch, section: Section) -> str:
    """The manifest path for a section -- e.g. batch "src/services" + section
    "auth" -> "src/services/auth". This is what path_mappings.path stores."""
    if batch.batch_key == ROOT_BATCH_KEY:
        return section.section_key
    return f"{batch.batch_key}/{section.section_key}"


def derive_section_path(path: str) -> str:
    """The section-level path a raw file path resolves to under the standard
    batch+section derivation, without needing an actual Batch/Section object
    built first. Used to map a renamed file's previous_path back to the
    section it used to belong to, so a rename can be matched against an
    existing PathMapping instead of always registering as brand new."""
    batch_key = _batch_key_for_path(path)
    section_key = _section_key(batch_key, path)
    if batch_key == ROOT_BATCH_KEY:
        return section_key
    return f"{batch_key}/{section_key}"


def partition_into_sections(batch: Batch) -> list[Section]:
    """A folder-level page is pre-partitioned into one section per immediate
    child path, from first generation -- this is what makes later promotion a
    mechanical cut (moving an existing section to its own page) rather than a
    fresh split decision. Applies to every batch, including messy/grab-bag
    folders, which is an accepted tradeoff, not a bug."""
    grouped: dict[str, list] = {}
    for change in batch.changes:
        key = _section_key(batch.batch_key, change.path)
        grouped.setdefault(key, []).append(change)

    return [Section(section_key=key, changes=changes) for key, changes in grouped.items()]
