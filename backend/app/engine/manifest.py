import hashlib

from sqlalchemy.orm import Session

from app.integrations.llm import propose_name_and_location
from app.models import NameOrigin, PathMapping, SyncStatus


def _generate_anchor(path: str) -> str:
    return "sec-" + hashlib.sha1(path.encode()).hexdigest()[:8]


def resolve_mapping(
    db: Session,
    repo_id: int,
    path: str,
    parent_path: str | None,
    sibling_paths: list[str],
    parent_mapping_id: int | None = None,
    parent_batch_mapping_id: int | None = None,
) -> PathMapping:
    """Looks up an existing path_mappings row for (repo_id, path). On first
    sighting -- no existing row -- proposes a name via the LLM and persists it,
    so every later sync of the same path is a plain lookup, not a fresh LLM call.

    A row whose removed_at is set (its prior DELETE write succeeded -- see
    confluence_writer._write_page_level/_write_section_level) is treated as
    a revival, not a live mapping: the path is being freshly recreated, so
    its content-identity fields are reset the same way a brand-new
    PathMapping would be (fresh LLM title proposal, reset promotion state,
    parent linkage taken from this call's fresh args), and removed_at is
    cleared. This only fires once per deletion -- after the first revival
    clears removed_at, later calls for the same path before human approval
    just return the row as-is, same as any other already-known path
    (classify_section / build_approval_records' existing _has_pending_approval
    guard prevents a duplicate proposal in that window).

    parent_mapping_id links a section to the batch-level page mapping that
    contains it; left None for batch-level (page) mappings themselves, whose
    parent is the repo's root page, not another PathMapping row.

    parent_batch_mapping_id is the batch-level counterpart: it links one
    batch/page-level mapping to another (e.g. "backend/lib" -> "backend"),
    for nesting Confluence pages to match real folder structure. Only ever
    set on batch-level mappings; always None for a top-level batch.
    """
    existing = db.query(PathMapping).filter_by(repo_id=repo_id, path=path).one_or_none()
    if existing is not None and existing.removed_at is None:
        return existing

    proposal = propose_name_and_location(path, parent_path, sibling_paths)

    if existing is not None:
        existing.title = proposal["title"]
        existing.name_origin = NameOrigin.LLM_PROPOSED
        existing.section_anchor = _generate_anchor(path)
        existing.parent_mapping_id = parent_mapping_id
        existing.parent_batch_mapping_id = parent_batch_mapping_id
        existing.page_id = None
        existing.is_promoted = False
        existing.is_promotable = False
        existing.sync_status = SyncStatus.PENDING
        existing.removed_at = None
        db.flush()
        return existing

    mapping = PathMapping(
        repo_id=repo_id,
        path=path,
        title=proposal["title"],
        name_origin=NameOrigin.LLM_PROPOSED,
        sync_status=SyncStatus.PENDING,
        parent_mapping_id=parent_mapping_id,
        parent_batch_mapping_id=parent_batch_mapping_id,
        section_anchor=_generate_anchor(path),
    )
    db.add(mapping)
    db.flush()
    return mapping
