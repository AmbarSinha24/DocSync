import json

from openai import OpenAI

from app.config import settings

MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.deepseek_api_key, base_url=DEEPSEEK_BASE_URL)
    return _client


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
    return text.strip()


def propose_name_and_location(
    path: str, parent_path: str | None, sibling_paths: list[str]
) -> dict:
    """First-sighting naming: propose a Confluence page title for a repo path.

    Called only once per path (on first sighting); the result is persisted
    to the path_mappings manifest and reused on every later sync.
    """
    prompt = f"""You are naming a documentation page for a path in a codebase. The \
Confluence space's structure takes inspiration from the codebase's structure but is \
not a literal 1:1 mirror.

Path being documented: {path}
Parent path in the doc hierarchy: {parent_path or "(top level)"}
Sibling paths already documented under the same parent: {sibling_paths or "(none yet)"}

Propose a short, human-readable page title for this path. Respond with JSON only, \
no other text: {{"title": "...", "rationale": "one sentence"}}"""

    response = _get_client().chat.completions.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_strip_code_fence(response.choices[0].message.content))


def generate_section_content(
    path: str,
    diff_patch: str,
    commit_messages: list[str],
    commit_sha: str,
    existing_content: str | None,
) -> str:
    """Generates the content that goes *inside* a GENERATED marker block (Confluence
    storage format / XHTML) for one section. Does not touch LOCKED content or anything
    outside the section -- that boundary is enforced by the Confluence writer, which
    never passes this function anything beyond the section's own generated portion.

    No separate PR-context lookup: commit messages (already fetched by the engine's
    read layer) are used as the "why" context instead, since a push doesn't reliably
    map to one PR and a second lookup call isn't justified by the marginal benefit.
    """
    messages_block = (
        "\n".join(f"- {m}" for m in commit_messages)
        if commit_messages
        else "(no commit messages available -- one-time snapshot mode)"
    )
    existing_block = (
        f"\n\nExisting generated content for this section (regenerate it fully, "
        f"don't just append):\n{existing_content}"
        if existing_content
        else ""
    )

    prompt = f"""Generate technical, developer-facing documentation content for a \
Confluence page section, in Confluence storage format (XHTML), for the path `{path}`.

Commit messages for this change:
{messages_block}

Diff:
{diff_patch}
{existing_block}

Write the content that goes inside a GENERATED block. Structure:
- One <p> stating the module path and a precise technical overview of what this \
path is responsible for -- technical, not descriptive.
- An <ac:structured-macro ac:name="code"> block (with an ac:parameter name="language" \
set correctly, and the code body wrapped in an ac:plain-text-body CDATA section) \
showing the relevant snippet -- a function signature, a config block, a migration's \
schema change, whatever's the meaningful unit for this file type.
- Technical prose covering behavior, types, return values, side effects, or failure \
modes -- whatever's actually relevant to this kind of file. Do not force this into a \
fixed table shape; adapt to what's being documented (params/returns for a function, \
keys/defaults for a config file, columns/constraints for a migration, etc).
- An <h3>Recent changes (commit {commit_sha[:7]})</h3> section with a <ul> of \
specific, technical changelog entries referencing exact names/paths from the diff.

Do not include the outer SECTION or GENERATED marker comments themselves -- only the \
content that goes inside them. Do not speculate beyond what the diff and commit \
messages show. Respond with the HTML content only, no other text."""

    response = _get_client().chat.completions.create(
        model=MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
