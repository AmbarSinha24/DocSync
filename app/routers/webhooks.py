import hashlib
import hmac
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings
from app.engine.orchestrator import TARGET_BRANCH, process_push

router = APIRouter()


def _verify_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="missing or malformed signature")

    expected = hmac.new(
        settings.github_webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")

    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="signature verification failed")


@router.post("/webhooks/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256"))

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="malformed JSON payload")

    event = request.headers.get("X-GitHub-Event")
    if event != "push":
        return {"status": "ignored", "reason": f"event type '{event}' is not 'push'"}

    ref = payload.get("ref")
    if ref != f"refs/heads/{TARGET_BRANCH}":
        return {"status": "ignored", "reason": f"ref '{ref}' is not the target branch"}

    try:
        owner = payload["repository"]["owner"]["login"]
        repo_name = payload["repository"]["name"]
        target_sha = payload["after"]
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"missing expected field: {e}")

    background_tasks.add_task(process_push, owner, repo_name, target_sha)
    return {"status": "accepted", "owner": owner, "repo": repo_name, "target_sha": target_sha}
