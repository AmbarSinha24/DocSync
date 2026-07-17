import re

# Plain HTML comments don't survive Confluence's storage-format processor -- they
# get silently stripped on save (verified empirically). Confluence's own "anchor"
# macro is structured macro data, not a raw comment, and does survive round-trips,
# so section/generated/locked boundaries are marked with paired anchor macros
# instead: {anchor}-start/-end for the section, {anchor}-gen-start/-end for the
# generated sub-block, {anchor}-locked-start/-end for an optional human-added block.

ANCHOR_MACRO_TEMPLATE = (
    '<ac:structured-macro ac:name="anchor" ac:schema-version="1">'
    '<ac:parameter ac:name="">{name}</ac:parameter></ac:structured-macro>'
)


class SectionNotFoundError(Exception):
    pass


def _anchor_marker(name: str) -> str:
    return ANCHOR_MACRO_TEMPLATE.format(name=name)


def _anchor_pattern_str(name: str) -> str:
    # tolerant of extra attributes (e.g. ac:macro-id) Confluence adds on save
    return (
        r'<ac:structured-macro ac:name="anchor"[^>]*>'
        r'<ac:parameter ac:name="">' + re.escape(name) + r"</ac:parameter>"
        r"</ac:structured-macro>"
    )


def _span_pattern(anchor: str, suffix: str) -> re.Pattern:
    return re.compile(
        _anchor_pattern_str(f"{anchor}-{suffix}-start")
        + r"(?P<body>.*?)"
        + _anchor_pattern_str(f"{anchor}-{suffix}-end"),
        re.DOTALL,
    )


def render_new_section(path: str, anchor: str, title: str, generated_html: str) -> str:
    """A brand-new SECTION block: title heading + GENERATED content, no LOCKED
    block (those only ever get added by a human directly in Confluence)."""
    return (
        f"{_anchor_marker(anchor + '-section-start')}\n"
        f"<h2>{title}</h2>\n\n"
        f"{_anchor_marker(anchor + '-gen-start')}\n"
        f"{generated_html}\n"
        f"{_anchor_marker(anchor + '-gen-end')}\n"
        f"{_anchor_marker(anchor + '-section-end')}"
    )


def insert_section(page_body: str, new_section_html: str) -> str:
    """Appends a new section to the page. Order among sections isn't meaningful
    yet in Phase 2 -- always appended at the end."""
    if page_body.strip():
        return page_body.rstrip() + "\n\n" + new_section_html
    return new_section_html


def get_generated_block(page_body: str, anchor: str) -> str | None:
    """Extracts the current content inside the GENERATED sub-block for the
    section matching `anchor`, without modifying anything. Returns None if
    the section (or its GENERATED block) doesn't exist, rather than raising --
    callers use this for read-only diffing, where "nothing there yet" is a
    normal, expected outcome, not an error."""
    section_match = _span_pattern(anchor, "section").search(page_body)
    if not section_match:
        return None

    gen_match = _span_pattern(anchor, "gen").search(section_match.group(0))
    if not gen_match:
        return None

    return gen_match.group("body").strip()


def replace_generated_block(page_body: str, anchor: str, new_generated_html: str) -> str:
    """Replaces only the GENERATED sub-block within the section matching
    `anchor`, leaving the title, any LOCKED block, and everything outside the
    section entirely untouched. Raises if the section doesn't exist -- callers
    should only call this for CONTENT_EDIT, where the section is expected to
    already be there."""
    section_pattern = _span_pattern(anchor, "section")
    section_match = section_pattern.search(page_body)
    if not section_match:
        raise SectionNotFoundError(f"no section found with anchor {anchor!r}")

    section_text = section_match.group(0)
    gen_pattern = _span_pattern(anchor, "gen")
    gen_match = gen_pattern.search(section_text)
    if not gen_match:
        raise SectionNotFoundError(f"section {anchor!r} has no GENERATED block to replace")

    new_section_text = (
        section_text[: gen_match.start()]
        + _anchor_marker(anchor + "-gen-start")
        + "\n"
        + new_generated_html
        + "\n"
        + _anchor_marker(anchor + "-gen-end")
        + section_text[gen_match.end() :]
    )

    return page_body[: section_match.start()] + new_section_text + page_body[section_match.end() :]


def remove_section(page_body: str, anchor: str) -> str:
    """Removes the entire SECTION block (title, GENERATED, and any LOCKED
    content) for the given anchor. Raises if it doesn't exist."""
    section_match = _span_pattern(anchor, "section").search(page_body)
    if not section_match:
        raise SectionNotFoundError(f"no section found with anchor {anchor!r}")

    before = page_body[: section_match.start()].rstrip()
    after = page_body[section_match.end() :].lstrip()
    if before and after:
        return before + "\n\n" + after
    return before or after
