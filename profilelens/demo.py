"""Deterministic fictional data for demos, tests, and screenshots."""

from __future__ import annotations

from datetime import UTC, datetime

from .audit import build_audit_report
from .models import (
    AuditReport,
    CommentAvailability,
    CommentRecord,
    ProbeResult,
    RecordSource,
)


def demo_report() -> AuditReport:
    """Build a report covering every important evidence state."""

    archived = [
        _comment("demo001", "A visible test comment.", "learnpython", "2026-09-20T15:00:00Z"),
        _comment(
            "demo002",
            "A live comment hidden from the profile listing.",
            "privacy",
            "2026-09-19T14:00:00Z",
        ),
        _comment(
            "demo003",
            "A comment later removed by moderators.",
            "examplesub",
            "2026-09-18T13:00:00Z",
        ),
        _comment(
            "demo004",
            "A comment later deleted by its author.",
            "examplesub",
            "2026-09-17T12:00:00Z",
        ),
        _comment(
            "demo005",
            "An archived comment whose current state is unavailable.",
            "opensource",
            "2026-09-16T11:00:00Z",
        ),
    ]
    public = [
        _comment(
            "demo001",
            "A visible test comment.",
            "learnpython",
            "2026-09-20T15:00:00Z",
            source=RecordSource.DEMO,
        ),
        _comment(
            "demo006",
            "A recent public comment that the archive has not captured yet.",
            "python",
            "2026-09-21T16:00:00Z",
            source=RecordSource.DEMO,
        ),
    ]
    probes = {
        "demo002": ProbeResult(
            CommentAvailability.LIVE,
            _comment(
                "demo002",
                "A live comment hidden from the profile listing.",
                "privacy",
                "2026-09-19T14:00:00Z",
                source=RecordSource.DEMO,
            ),
        ),
        "demo003": ProbeResult(
            CommentAvailability.REMOVED,
            _comment(
                "demo003",
                "[removed]",
                "examplesub",
                "2026-09-18T13:00:00Z",
                source=RecordSource.DEMO,
            ),
        ),
        "demo004": ProbeResult(
            CommentAvailability.DELETED,
            _comment(
                "demo004",
                "[deleted]",
                "examplesub",
                "2026-09-17T12:00:00Z",
                source=RecordSource.DEMO,
            ),
        ),
        "demo005": ProbeResult(CommentAvailability.UNAVAILABLE),
    }
    return build_audit_report(
        "demo_account",
        archived,
        public,
        public_profile_compared=True,
        requested_public_limit=100,
        probe=lambda comment_id: probes[comment_id],
        max_probes=10,
    )


def _comment(
    comment_id: str,
    body: str,
    subreddit: str,
    created_utc: str,
    *,
    source: RecordSource = RecordSource.DEMO,
) -> CommentRecord:
    post_id = "demo_post"
    return CommentRecord(
        id=comment_id,
        author="demo_account",
        subreddit=subreddit,
        body=body,
        created_utc=datetime.fromisoformat(created_utc.replace("Z", "+00:00")).astimezone(UTC),
        source=source,
        permalink=f"/r/{subreddit}/comments/{post_id}/example/{comment_id}/",
        score=1,
        link_id=f"t3_{post_id}",
    )
