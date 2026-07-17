import httpx

from app.config import settings


class ConfluenceClient:
    """Thin wrapper around the Confluence Cloud REST API v2."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            auth=(email, api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def get_page(self, page_id: str, include_body: bool = False) -> dict:
        params = {"body-format": "storage"} if include_body else {}
        resp = self._client.get(f"{self.base_url}/wiki/api/v2/pages/{page_id}", params=params)
        resp.raise_for_status()
        return resp.json()

    def create_page(self, space_id: str, parent_id: str, title: str, html_body: str) -> dict:
        payload = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
            "parentId": parent_id,
            "body": {"representation": "storage", "value": html_body},
        }
        resp = self._client.post(f"{self.base_url}/wiki/api/v2/pages", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_page(self, page_id: str, title: str, html_body: str, current_version: int) -> dict:
        payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": html_body},
            "version": {"number": current_version + 1},
        }
        resp = self._client.put(f"{self.base_url}/wiki/api/v2/pages/{page_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete_page(self, page_id: str) -> None:
        resp = self._client.delete(f"{self.base_url}/wiki/api/v2/pages/{page_id}")
        resp.raise_for_status()


def get_confluence_client() -> ConfluenceClient:
    return ConfluenceClient(
        base_url=settings.confluence_base_url,
        email=settings.confluence_email,
        api_token=settings.confluence_api_token,
    )
