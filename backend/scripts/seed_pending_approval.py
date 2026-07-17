"""Seeds one fresh pending CONTENT_EDIT approval against the real fixture repo,
for the Playwright end-to-end UI test to act on. Reuses the real engine
pipeline (GitHub MCP diff + DeepSeek generation + live Confluence content
fetch) -- this is a real integration fixture, not mock data."""

import asyncio

from app.db import SessionLocal
from app.engine.approval_builder import build_approval_records
from app.engine.core import generate_changeset
from app.models import Repo, RepoSourceType

FIXTURE_OWNER = "AmbarSinha24"
FIXTURE_REPO = "docsync-fixture"
INITIAL_SHA = "e457ed87a419541171c945182bcefd2ba5ebfa16"
SECOND_SHA = "17636e4648d1499b37977718ee89d4aa36ad4364"
FIXTURE_ROOT_PAGE_ID = "950273"


async def main():
    db = SessionLocal()
    repo = db.query(Repo).filter_by(name=f"{FIXTURE_OWNER}/{FIXTURE_REPO}").one_or_none()
    if repo is None:
        repo = Repo(
            name=f"{FIXTURE_OWNER}/{FIXTURE_REPO}",
            source_type=RepoSourceType.GITHUB_APP,
            root_page_id=FIXTURE_ROOT_PAGE_ID,
        )
        db.add(repo)
        db.commit()

    changeset = await generate_changeset(FIXTURE_OWNER, FIXTURE_REPO, SECOND_SHA, INITIAL_SHA)
    records = build_approval_records(db, repo.id, changeset)
    db.commit()

    for r in records:
        print(f"SEEDED_APPROVAL_ID={r.id} path={r.path_mapping.path} type={r.change_type.value}")

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
