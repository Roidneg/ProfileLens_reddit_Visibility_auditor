"""ProfileLens: evidence-based Reddit profile visibility auditing."""

from .audit import build_audit_report
from .models import AuditReport, AuditRow, AuditStatus, CommentRecord
from .parsing import ProfileInputError, extract_username

__all__ = [
    "AuditReport",
    "AuditRow",
    "AuditStatus",
    "CommentRecord",
    "ProfileInputError",
    "build_audit_report",
    "extract_username",
]

__version__ = "0.1.0"
