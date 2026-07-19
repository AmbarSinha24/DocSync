from app.models import ApprovalRecord

SUMMARY_MAX_LENGTH = 200


def build_audit_summary(record: ApprovalRecord) -> str:
    """Short, human-readable line describing what an audit entry was about --
    change_type + path, plus the proposed name for CREATE/RENAME. This is the
    only context that survives once proposed_content/current_content/
    diff_patch/pr_context are cleared after a record resolves (see
    confluence_writer.write_approval's success path and approvals.reject), so
    it must be populated on every AuditLog entry going forward."""
    summary = f"{record.change_type.value} on {record.path_mapping.path}"
    if record.proposed_name:
        summary += f' -> "{record.proposed_name}"'
    return summary[:SUMMARY_MAX_LENGTH]
