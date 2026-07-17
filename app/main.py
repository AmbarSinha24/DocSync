from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import approvals, webhooks

app = FastAPI(title="Docs-as-Code Sync Engine")
app.include_router(webhooks.router)
app.include_router(approvals.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}
