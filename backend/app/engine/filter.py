import pathspec

from app.engine.models import Changeset

DEFAULT_EXCLUDE_PATTERNS = [
    # tests
    "**/test/**",
    "**/tests/**",
    "**/__tests__/**",
    "**/*_test.*",
    "**/*.test.*",
    "**/*.spec.*",
    # vendor / dependencies
    "node_modules/**",
    "vendor/**",
    "venv/**",
    ".venv/**",
    "**/site-packages/**",
    # build / generated artifacts
    "dist/**",
    "build/**",
    "**/__pycache__/**",
    "*.pyc",
    "*.min.js",
    "*.generated.*",
    # lockfiles
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    "poetry.lock",
    "*.lock",
    # db migrations (often auto-generated, noisy)
    "**/migrations/**",
    "**/alembic/versions/**",
    # vcs / editor / ci noise
    ".git/**",
    ".github/**",
    ".vscode/**",
    ".idea/**",
    # binary / media
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.ico",
    "*.woff",
    "*.woff2",
    "*.ttf",
]


def doc_worthy_filter(changeset: Changeset, extra_exclude_patterns: list[str] | None = None) -> Changeset:
    """Drops noise paths (tests, vendor, generated code, lockfiles, etc.) before
    anything else -- LOC guardrail, batching, and LLM calls all operate on what's
    left, so excluded paths never count against cost or trigger generation."""
    patterns = DEFAULT_EXCLUDE_PATTERNS + (extra_exclude_patterns or [])
    spec = pathspec.PathSpec.from_lines("gitignore", patterns)

    kept = [change for change in changeset.changes if not spec.match_file(change.path)]

    return Changeset(
        owner=changeset.owner,
        repo=changeset.repo,
        target_sha=changeset.target_sha,
        baseline_sha=changeset.baseline_sha,
        changes=kept,
        commit_messages=changeset.commit_messages,
    )
