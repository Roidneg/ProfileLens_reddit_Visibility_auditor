"""Core data models used by the archive and live-data adapters."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RecordSource(StrEnum):
    """Origin of a comment record."""

    ARCTIC_SHIFT = "Arctic Shift"
    REDDIT_PUBLIC_PROFILE = "Reddit public profile"
    REDDIT_DIRECT_LOOKUP = "Reddit direct lookup"
    DEMO = "Demonstration data"


class CommentAvailability(StrEnum):
    """Current state returned by a direct Reddit comment lookup."""

    LIVE = "live"
    REMOVED = "removed"
    DELETED = "deleted"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"


class AuditStatus(StrEnum):
    """Evidence-based classifications produced by an audit."""

    VISIBLE = "Visible on public profile"
    LIVE_NOT_LISTED = "Live but not listed on profile"
    ARCHIVED_NOT_LISTED = "Archived but not listed"
    REMOVED = "Removed by moderator"
    DELETED = "Deleted"
    ARCHIVE_ONLY = "Archive only"
    ARCHIVED_NOT_COMPARED = "Archived; public profile not compared"
    OUTSIDE_WINDOW = "Outside comparison window"
    VISIBLE_NOT_ARCHIVED = "Visible; not found in archive"
    UNKNOWN = "Unknown"


def normalize_comment_id(value: str) -> str:
    """Return a Reddit comment ID without its optional ``t1_`` prefix."""

    normalized = str(value or "").strip()
    if normalized.lower().startswith("t1_"):
        normalized = normalized[3:]
    if not normalized:
        raise ValueError("A comment ID is required.")
    return normalized


def utc_datetime(value: datetime | int | float | str) -> datetime:
    """Normalize common timestamp representations to an aware UTC datetime."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=UTC)
    elif isinstance(value, str):
        candidate = value.strip()
        if candidate.replace(".", "", 1).isdigit():
            parsed = datetime.fromtimestamp(float(candidate), tz=UTC)
        else:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    else:
        raise TypeError(f"Unsupported timestamp type: {type(value)!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CommentRecord:
    """A normalized comment from either an archive or Reddit itself."""

    id: str
    author: str
    subreddit: str
    body: str
    created_utc: datetime
    source: RecordSource
    permalink: str | None = None
    score: int | None = None
    link_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", normalize_comment_id(self.id))
        object.__setattr__(self, "created_utc", utc_datetime(self.created_utc))
        object.__setattr__(self, "author", str(self.author or "[unknown]"))
        object.__setattr__(self, "subreddit", str(self.subreddit or "[unknown]"))
        object.__setattr__(self, "body", str(self.body or ""))

    @property
    def reddit_url(self) -> str | None:
        if not self.permalink:
            return None
        if self.permalink.startswith("http://") or self.permalink.startswith("https://"):
            return self.permalink
        return f"https://www.reddit.com{self.permalink}"

    def to_dict(self, *, include_body: bool = True) -> dict[str, Any]:
        body = self.body if include_body else _body_preview(self.body)
        return {
            "comment_id": self.id,
            "author": self.author,
            "subreddit": self.subreddit,
            "body": body,
            "created_utc": self.created_utc.isoformat(),
            "score": self.score,
            "source": self.source.value,
            "permalink": self.reddit_url,
            "link_id": self.link_id,
        }


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Result of checking one archived comment against Reddit."""

    availability: CommentAvailability
    record: CommentRecord | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class AuditRow:
    """One row in the evidence report."""

    comment_id: str
    status: AuditStatus
    confidence: str
    interpretation: str
    author: str
    subreddit: str
    created_utc: datetime
    permalink: str | None
    archive_body: str = ""
    current_body: str = ""
    archive_score: int | None = None
    on_public_profile: bool = False
    direct_lookup: CommentAvailability = CommentAvailability.NOT_CHECKED

    def to_dict(self, *, include_body: bool = False) -> dict[str, Any]:
        archive_body = self.archive_body if include_body else _body_preview(self.archive_body)
        current_body = self.current_body if include_body else _body_preview(self.current_body)
        return {
            "comment_id": self.comment_id,
            "status": self.status.value,
            "confidence": self.confidence,
            "interpretation": self.interpretation,
            "author": self.author,
            "subreddit": self.subreddit,
            "created_utc": self.created_utc.isoformat(),
            "on_public_profile": self.on_public_profile,
            "direct_lookup": self.direct_lookup.value,
            "archive_score": self.archive_score,
            "archive_body": archive_body,
            "current_body": current_body,
            "permalink": self.permalink,
        }


@dataclass(slots=True)
class AuditReport:
    """Complete result and methodology metadata for one audit run."""

    username: str
    rows: list[AuditRow]
    archive_count: int
    public_profile_count: int
    public_profile_compared: bool
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    public_oldest_utc: datetime | None = None
    public_limit_reached: bool = False
    probes_run: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts = Counter(row.status.value for row in self.rows)
        return dict(sorted(counts.items()))

    def to_dict(self, *, include_body: bool = False) -> dict[str, Any]:
        return {
            "metadata": {
                "username": self.username,
                "generated_at": self.generated_at.isoformat(),
                "archive_count": self.archive_count,
                "public_profile_count": self.public_profile_count,
                "public_profile_compared": self.public_profile_compared,
                "public_oldest_utc": (
                    self.public_oldest_utc.isoformat() if self.public_oldest_utc else None
                ),
                "public_limit_reached": self.public_limit_reached,
                "direct_lookups_run": self.probes_run,
                "notes": self.notes,
                "summary": self.summary,
            },
            "results": [row.to_dict(include_body=include_body) for row in self.rows],
        }


def _body_preview(body: str, length: int = 180) -> str:
    collapsed = " ".join(str(body or "").split())
    if len(collapsed) <= length:
        return collapsed
    return f"{collapsed[: length - 1].rstrip()}…"
