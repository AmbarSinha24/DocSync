from datetime import datetime, timezone

from app.config import settings
from app.integrations.confluence import get_confluence_client


def test_root_page_is_reachable():
    client = get_confluence_client()
    page = client.get_page(settings.confluence_root_page_id)
    assert page["id"] == str(settings.confluence_root_page_id)
    assert page["title"]


def test_can_create_child_page_under_root():
    client = get_confluence_client()
    root = client.get_page(settings.confluence_root_page_id)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    new_page = client.create_page(
        space_id=root["spaceId"],
        parent_id=settings.confluence_root_page_id,
        title=f"Phase 0 Smoke Test ({stamp})",
        html_body="<p>Created by the docs-sync-engine Phase 0 smoke test. Safe to delete.</p>",
    )
    assert new_page["id"]
