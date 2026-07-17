import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RepoSourceType(str, enum.Enum):
    GITHUB_APP = "github_app"
    PUBLIC_SNAPSHOT = "public_snapshot"


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class NameOrigin(str, enum.Enum):
    LLM_PROPOSED = "llm_proposed"
    HUMAN_EDITED = "human_edited"


class ChangeType(str, enum.Enum):
    CREATE = "create"
    PROMOTE = "promote"
    RENAME = "rename"
    DELETE = "delete"
    CONTENT_EDIT = "content_edit"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AuditAction(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    REGENERATED = "regenerated"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source_type: Mapped[RepoSourceType] = mapped_column(Enum(RepoSourceType), nullable=False)
    github_installation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    root_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structural_approver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_approver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    path_mappings: Mapped[list["PathMapping"]] = relationship(back_populates="repo")
    jobs: Mapped[list["Job"]] = relationship(back_populates="repo")


class PathMapping(Base):
    __tablename__ = "path_mappings"
    __table_args__ = (UniqueConstraint("repo_id", "path", name="uq_repo_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("path_mappings.id"), nullable=True
    )
    section_anchor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus), nullable=False, default=SyncStatus.PENDING
    )
    last_synced_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_promoted: Mapped[bool] = mapped_column(default=False)
    name_origin: Mapped[NameOrigin | None] = mapped_column(Enum(NameOrigin), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    repo: Mapped["Repo"] = relationship(back_populates="path_mappings")
    parent: Mapped["PathMapping | None"] = relationship(remote_side=[id])
    approval_records: Mapped[list["ApprovalRecord"]] = relationship(back_populates="path_mapping")


class ApprovalRecord(Base):
    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_mapping_id: Mapped[int] = mapped_column(ForeignKey("path_mappings.id"), nullable=False)
    change_type: Mapped[ChangeType] = mapped_column(Enum(ChangeType), nullable=False)
    proposed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_location: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pr_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING
    )
    approver: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    path_mapping: Mapped["PathMapping"] = relationship(back_populates="approval_records")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="approval_record")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_record_id: Mapped[int] = mapped_column(
        ForeignKey("approval_records.id"), nullable=False
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pr_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    approval_record: Mapped["ApprovalRecord"] = relationship(back_populates="audit_entries")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), nullable=False)
    batch_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), nullable=False, default=JobStatus.QUEUED
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    repo: Mapped["Repo"] = relationship(back_populates="jobs")
