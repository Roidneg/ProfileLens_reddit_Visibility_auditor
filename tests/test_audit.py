from profilelens.audit import build_audit_report
from profilelens.models import (
    AuditStatus,
    CommentAvailability,
    CommentRecord,
    ProbeResult,
    RecordSource,
)


def make_comment(comment_id, created, body="body", source=RecordSource.ARCTIC_SHIFT):
    return CommentRecord(
        id=comment_id,
        author="test_user",
        subreddit="testing",
        body=body,
        created_utc=created,
        source=source,
        permalink=f"/r/testing/comments/post/title/{comment_id}/",
    )


def test_audit_classifies_visible_and_live_not_listed():
    archived = [
        make_comment("same", "2026-09-20T12:00:00Z"),
        make_comment("missing", "2026-09-19T12:00:00Z"),
    ]
    public = [
        make_comment("same", "2026-09-20T12:00:00Z", source=RecordSource.REDDIT_PUBLIC_PROFILE)
    ]

    report = build_audit_report(
        "test_user",
        archived,
        public,
        public_profile_compared=True,
        requested_public_limit=100,
        probe=lambda _: ProbeResult(
            CommentAvailability.LIVE,
            make_comment(
                "missing",
                "2026-09-19T12:00:00Z",
                source=RecordSource.REDDIT_DIRECT_LOOKUP,
            ),
        ),
    )

    statuses = {row.comment_id: row.status for row in report.rows}
    assert statuses == {
        "same": AuditStatus.VISIBLE,
        "missing": AuditStatus.LIVE_NOT_LISTED,
    }
    assert report.probes_run == 1


def test_audit_classifies_probe_markers():
    archived = [
        make_comment("removed", "2026-09-20T12:00:00Z"),
        make_comment("deleted", "2026-09-19T12:00:00Z"),
        make_comment("unavailable", "2026-09-18T12:00:00Z"),
    ]
    outcomes = {
        "removed": CommentAvailability.REMOVED,
        "deleted": CommentAvailability.DELETED,
        "unavailable": CommentAvailability.UNAVAILABLE,
    }
    report = build_audit_report(
        "test_user",
        archived,
        public_profile_compared=True,
        probe=lambda comment_id: ProbeResult(outcomes[comment_id]),
    )
    statuses = {row.comment_id: row.status for row in report.rows}
    assert statuses["removed"] is AuditStatus.REMOVED
    assert statuses["deleted"] is AuditStatus.DELETED
    assert statuses["unavailable"] is AuditStatus.ARCHIVE_ONLY


def test_capped_listing_marks_older_archive_record_outside_window():
    archived = [
        make_comment("visible", "2026-09-20T12:00:00Z"),
        make_comment("older", "2020-01-01T12:00:00Z"),
    ]
    public = [
        make_comment(
            "visible",
            "2026-09-20T12:00:00Z",
            source=RecordSource.REDDIT_PUBLIC_PROFILE,
        )
    ]
    report = build_audit_report(
        "test_user",
        archived,
        public,
        public_profile_compared=True,
        requested_public_limit=1,
        probe=lambda _: (_ for _ in ()).throw(AssertionError("probe should not run")),
    )
    statuses = {row.comment_id: row.status for row in report.rows}
    assert statuses["older"] is AuditStatus.OUTSIDE_WINDOW
    assert report.public_limit_reached is True
    assert report.probes_run == 0


def test_archive_only_mode_does_not_claim_profile_absence():
    report = build_audit_report(
        "test_user",
        [make_comment("archived", "2026-09-20T12:00:00Z")],
    )
    assert report.rows[0].status is AuditStatus.ARCHIVED_NOT_COMPARED
