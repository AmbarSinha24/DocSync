# Self-Hosting Guide

This engine is self-hosted: each adopter runs their own copy against their own
Confluence space and GitHub repos, with their own credentials. There is no
shared multi-tenant service.

## Prerequisites

- Python 3.12+
- Node.js (for the frontend)
- A MySQL-compatible database. [TiDB Cloud](https://tidbcloud.com)'s free
  serverless tier is a good default (no server to run yourself, TLS by
  default) — any MySQL 8-compatible database works.
- A Confluence space you can create pages in
- A GitHub account with a personal access token (repo read access) for the
  repos you want documented
- A public HTTPS URL for your backend once deployed (GitHub needs to be able
  to reach your webhook endpoint — a plain `localhost` won't work for real
  push events, though it's fine for local testing via the Add-Repo UI)

## Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# now edit .env -- see "Obtaining credentials" below

alembic upgrade head
uvicorn app.main:app --reload
```

The backend serves on `http://localhost:8000` by default. Confirm it's up:

```bash
curl http://localhost:8000/health
```

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
# for local dev against a locally-running backend, .env can stay empty --
# the Vite dev server proxies /api to localhost:8000 automatically.
npm run dev
```

For a production build (e.g. deploying to Vercel), set `VITE_API_BASE_URL` in
`.env` to your deployed backend's origin first, then `npm run build`.

## Obtaining credentials

- **Confluence API token**: generate one at
  https://id.atlassian.com/manage-profile/security/api-tokens. Use it as
  `CONFLUENCE_API_TOKEN` alongside the email address of the account that
  created it (`CONFLUENCE_EMAIL`).
- **Confluence root page ID**: create (or pick) a page in your space to act
  as the parent for all synced repos' docs. Open it in Confluence and read
  the numeric ID out of the URL — use that as `CONFLUENCE_ROOT_PAGE_ID`.
- **GitHub PAT**: create a fine-grained token with read access to Contents
  and Metadata for the repos you'll sync. Use it as `GITHUB_MCP_TOKEN`.
- **GitHub webhook secret**: any random string works — generate one with
  `openssl rand -hex 32` and use it as `GITHUB_WEBHOOK_SECRET`. You'll enter
  the same value into GitHub's webhook config in the last step below.

## Deploying

Deploy the backend somewhere with a public HTTPS URL (e.g. an EC2 instance
behind nginx + TLS) and the frontend as a static build (e.g. Vercel). Point
the frontend's `VITE_API_BASE_URL` at the backend's public URL, and set the
backend's `CORS_ALLOWED_ORIGINS` to the frontend's public URL so the browser
is allowed to call it.

## Onboarding a repo

1. Open the frontend, use the **Add Repo** form with the repo's GitHub URL.
   This does three things: creates the repo's root page under your
   Confluence root page, detects and stores the repo's default branch, and
   runs an initial full sync producing approval records for you to review.
2. Once that's done, go to the repo's **Settings → Webhooks → Add webhook**
   on GitHub:
   - Payload URL: `https://<your-backend-host>/webhooks/github`
   - Content type: `application/json`
   - Secret: the same value as `GITHUB_WEBHOOK_SECRET`
   - Events: just `push`

From then on, every push to that repo's default branch triggers an
incremental sync automatically.

Note: a repo must be added through the UI (step 1) before its webhook
pushes will do anything — pushes for repos that haven't been onboarded yet
are ignored cleanly, since onboarding is what creates the Confluence root
page the sync needs to write into.
