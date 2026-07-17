from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.engine.batcher import batch_by_level2
from app.engine.core import generate_changeset
from app.engine.github_reader import _aggregate_files
from app.engine.guardrail import enforce_loc_guardrail
from app.engine.manifest import resolve_mapping
from app.engine.models import Changeset, FileChange, RepoTooLargeError
from app.engine.sectioner import partition_into_sections
from app.models import Repo, RepoSourceType

FIXTURE_OWNER = "AmbarSinha24"
FIXTURE_REPO = "docsync-fixture"
INITIAL_SHA = "e457ed87a419541171c945182bcefd2ba5ebfa16"
SECOND_SHA = "17636e4648d1499b37977718ee89d4aa36ad4364"

EXPECTED_DOC_WORTHY_PATHS = {
    "README.md",
    "src/config.py",
    "src/services/auth/login.py",
    "src/services/auth/session.py",
    "src/services/billing/invoice.py",
    "src/utils/helpers.py",
    "src/utils/formatters.py",
    "src/utils/misc.py",
}
EXPECTED_EXCLUDED_PATHS = {
    "tests/test_login.py",
    "node_modules/fake-package/index.js",
    "package-lock.json",
}


@pytest.mark.asyncio
async def test_null_baseline_produces_full_filtered_tree():
    cs = await generate_changeset(FIXTURE_OWNER, FIXTURE_REPO, INITIAL_SHA, None)
    paths = {c.path for c in cs.changes}

    assert paths == EXPECTED_DOC_WORTHY_PATHS
    assert paths.isdisjoint(EXPECTED_EXCLUDED_PATHS)
    assert all(c.status == "added" for c in cs.changes)


@pytest.mark.asyncio
async def test_incremental_diff_produces_only_the_real_changeset():
    cs = await generate_changeset(FIXTURE_OWNER, FIXTURE_REPO, SECOND_SHA, INITIAL_SHA)
    by_path = {c.path: c for c in cs.changes}

    assert set(by_path.keys()) == {
        "src/services/billing/invoice.py",
        "src/services/billing/receipt.py",
    }
    assert by_path["src/services/billing/invoice.py"].status == "modified"
    assert by_path["src/services/billing/receipt.py"].status == "added"


@pytest.mark.asyncio
async def test_doc_worthy_filter_excludes_noise_from_real_repo():
    cs = await generate_changeset(FIXTURE_OWNER, FIXTURE_REPO, INITIAL_SHA, None)
    paths = {c.path for c in cs.changes}
    for excluded in EXPECTED_EXCLUDED_PATHS:
        assert excluded not in paths


def test_rename_status_aggregated_as_a_move_not_delete_add():
    """GitHub's real rename heuristic can't be reliably triggered through the
    available write tools (delete + create are always separate commits, and
    rename detection only fires within a single commit's parent-diff). This
    isolates our own aggregation logic against GitHub's documented response
    shape for a renamed file instead."""
    commits_files = [
        [
            {
                "filename": "src/services/auth/sessions.py",
                "previous_filename": "src/services/auth/session.py",
                "status": "renamed",
                "additions": 0,
                "deletions": 0,
                "patch": None,
            }
        ]
    ]
    result = _aggregate_files(commits_files)

    assert len(result) == 1
    change = result[0]
    assert change.path == "src/services/auth/sessions.py"
    assert change.status == "renamed"
    assert change.previous_path == "src/services/auth/session.py"


def test_loc_guardrail_passes_under_cap():
    small = Changeset(
        owner="x", repo="y", target_sha="a", baseline_sha=None,
        changes=[FileChange(path="a.py", status="added", size_bytes=1000)],
    )
    enforce_loc_guardrail(small)  # should not raise


def test_loc_guardrail_blocks_over_cap_with_zero_llm_calls():
    huge = Changeset(
        owner="x", repo="y", target_sha="a", baseline_sha=None,
        changes=[FileChange(path=f"f{i}.py", status="added", size_bytes=50_000) for i in range(50)],
    )

    with patch("app.integrations.llm.propose_name_and_location") as mock_propose, \
         patch("app.integrations.llm.generate_section_content") as mock_generate:
        with pytest.raises(RepoTooLargeError):
            enforce_loc_guardrail(huge)

        mock_propose.assert_not_called()
        mock_generate.assert_not_called()


def test_llm_naming_fires_only_on_first_sighting(db: Session):
    repo = Repo(name="test/phase1-naming-check", source_type=RepoSourceType.GITHUB_APP)
    db.add(repo)
    db.flush()

    with patch(
        "app.engine.manifest.propose_name_and_location",
        return_value={"title": "Auth Service", "rationale": "test"},
    ) as mock_propose:
        first = resolve_mapping(db, repo.id, "src/services/auth", "src/services", [])
        second = resolve_mapping(db, repo.id, "src/services/auth", "src/services", [])

        assert first.id == second.id
        assert mock_propose.call_count == 1


def test_level2_batching_and_section_partitioning_together():
    cs = Changeset(
        owner="x", repo="y", target_sha="a", baseline_sha=None,
        changes=[
            FileChange(path="README.md", status="added"),
            FileChange(path="src/services/auth/login.py", status="added"),
            FileChange(path="src/services/auth/session.py", status="modified"),
            FileChange(path="src/services/billing/invoice.py", status="added"),
        ],
    )
    batches = {b.batch_key: b for b in batch_by_level2(cs)}

    assert set(batches.keys()) == {"(root)", "src/services"}

    sections = {s.section_key: s for s in partition_into_sections(batches["src/services"])}
    assert set(sections.keys()) == {"auth", "billing"}
    assert len(sections["auth"].changes) == 2
    assert len(sections["billing"].changes) == 1
