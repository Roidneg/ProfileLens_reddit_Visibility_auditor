"""Evidence classification and archive/live comparison logic."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .models import (
    AuditReport,
    AuditRow,
    AuditStatus,
    CommentAvailability,
    CommentRecord,
    ProbeResult,
)

Probe = Callable[[str], ProbeResult]


def build_audit_report(
    username: str,
    archived_comments: Sequence[CommentRecord],
    public_comments: Sequence[CommentRecord] = (),
    *,
    public_profile_compared: bool = False,
    requested_public_limit: int = 100,
    probe: Probe | None = None,
    max_probes: int = 20,
) -> AuditReport:
    """Compare normalized comment sets without overstating ambiguous evidence."""

    archive_by_id = _newest_by_id(archived_comments)
    public_by_id = _newest_by_id(public_comments)
    public_oldest = (
        min(item.created_utc for item in public_by_id.values()) if public_by_id else None
    )
    public_limit_reached = public_profile_compared and len(public_by_id) >= requested_public_limit

    rows: list[AuditRow] = []
    probes_run = 0

    for comment_id in sorted(
        set(archive_by_id) | set(public_by_id),
        key=lambda cid: _row_date(cid, archive_by_id, public_by_id),
        reverse=True,
    ):
        archived = archive_by_id.get(comment_id)
        public = public_by_id.get(comment_id)

        if archived and public:
            rows.append(
                _row(
                    archived,
                    status=AuditStatus.VISIBLE,
                    confidence="High",
                    interpretation="The comment appears in both the archive and public profile listing.",
                    public=public,
                    on_public_profile=True,
                )
            )
            continue

        if public and not archived:
            rows.append(
                _row(
                    public,
                    status=AuditStatus.VISIBLE_NOT_ARCHIVED,
                    confidence="High",
                    interpretation="The comment is currently public but was not returned by the archive query.",
                    public=public,
                    on_public_profile=True,
                )
            )
            continue

        assert archived is not None
        if not public_profile_compared:
            rows.append(
                _row(
                    archived,
                    status=AuditStatus.ARCHIVED_NOT_COMPARED,
                    confidence="Not assessed",
                    interpretation="Archive evidence exists; no live public-profile comparison was run.",
                )
            )
            continue

        outside_window = bool(
            public_limit_reached and public_oldest and archived.created_utc < public_oldest
        )
        if outside_window:
            rows.append(
                _row(
                    archived,
                    status=AuditStatus.OUTSIDE_WINDOW,
                    confidence="Not assessed",
                    interpretation=(
                        "The comment is older than the oldest item in a capped public listing, "
                        "so its absence is not evidence of profile curation."
                    ),
                )
            )
            continue

        result: ProbeResult | None = None
        if probe is not None and probes_run < max(0, max_probes):
            result = probe(comment_id)
            probes_run += 1

        if result is None:
            rows.append(
                _row(
                    archived,
                    status=AuditStatus.ARCHIVED_NOT_LISTED,
                    confidence="Medium",
                    interpretation=(
                        "The archive contains this comment, but the public profile listing does not. "
                        "A direct lookup was not run, so the reason remains unresolved."
                    ),
                )
            )
        else:
            rows.append(_classify_probe(archived, result))

    notes = [
        "Profile absence alone is not proof of deletion, moderation, or profile curation.",
        "Archive coverage is incomplete and third-party service availability can vary.",
    ]
    if public_limit_reached:
        notes.append(
            "The requested public listing limit was reached; older comments were excluded from comparison claims."
        )

    return AuditReport(
        username=username,
        rows=rows,
        archive_count=len(archive_by_id),
        public_profile_count=len(public_by_id),
        public_profile_compared=public_profile_compared,
        public_oldest_utc=public_oldest,
        public_limit_reached=public_limit_reached,
        probes_run=probes_run,
        notes=notes,
    )


def _classify_probe(archived: CommentRecord, result: ProbeResult) -> AuditRow:
    current = result.record
    if result.availability is CommentAvailability.LIVE:
        return _row(
            archived,
            status=AuditStatus.LIVE_NOT_LISTED,
            confidence="High",
            interpretation=(
                "The comment remains directly retrievable but is absent from the compared public profile window. "
                "This is strong evidence of profile-level filtering or curation."
            ),
            public=current,
            direct_lookup=result.availability,
        )
    if result.availability is CommentAvailability.REMOVED:
        return _row(
            archived,
            status=AuditStatus.REMOVED,
            confidence="High",
            interpretation="Reddit currently returns a moderator-removal marker for this comment.",
            public=current,
            direct_lookup=result.availability,
        )
    if result.availability is CommentAvailability.DELETED:
        return _row(
            archived,
            status=AuditStatus.DELETED,
            confidence="High",
            interpretation="Reddit currently returns a user-deletion marker for this comment.",
            public=current,
            direct_lookup=result.availability,
        )
    if result.availability is CommentAvailability.UNAVAILABLE:
        return _row(
            archived,
            status=AuditStatus.ARCHIVE_ONLY,
            confidence="Low",
            interpretation=(
                "The archive contains a record, but Reddit did not return the comment directly. "
                "The current cause cannot be determined."
            ),
            direct_lookup=result.availability,
        )
    return _row(
        archived,
        status=AuditStatus.UNKNOWN,
        confidence="Low",
        interpretation="The available sources were insufficient to classify this comment.",
        public=current,
        direct_lookup=result.availability,
    )


def _row(
    archived: CommentRecord,
    *,
    status: AuditStatus,
    confidence: str,
    interpretation: str,
    public: CommentRecord | None = None,
    on_public_profile: bool = False,
    direct_lookup: CommentAvailability = CommentAvailability.NOT_CHECKED,
) -> AuditRow:
    link = (public.reddit_url if public else None) or archived.reddit_url
    return AuditRow(
        comment_id=archived.id,
        status=status,
        confidence=confidence,
        interpretation=interpretation,
        author=public.author if public else archived.author,
        subreddit=public.subreddit if public else archived.subreddit,
        created_utc=public.created_utc if public else archived.created_utc,
        permalink=link,
        archive_body=archived.body,
        current_body=public.body if public else "",
        archive_score=archived.score,
        on_public_profile=on_public_profile,
        direct_lookup=direct_lookup,
    )


def _newest_by_id(comments: Sequence[CommentRecord]) -> dict[str, CommentRecord]:
    result: dict[str, CommentRecord] = {}
    for comment in comments:
        existing = result.get(comment.id)
        if existing is None or comment.created_utc > existing.created_utc:
            result[comment.id] = comment
    return result


def _row_date(
    comment_id: str,
    archive_by_id: dict[str, CommentRecord],
    public_by_id: dict[str, CommentRecord],
):
    record = public_by_id.get(comment_id) or archive_by_id[comment_id]
    return record.created_utc
