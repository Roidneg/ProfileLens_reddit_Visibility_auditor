"""Network adapters for Arctic Shift and Reddit's approved Data API."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import (
    CommentAvailability,
    CommentRecord,
    ProbeResult,
    RecordSource,
    utc_datetime,
)


class DataSourceError(RuntimeError):
    """Raised when a configured data source cannot complete a request."""


class ConfigurationError(RuntimeError):
    """Raised when optional Reddit API access is incomplete or unapproved."""


class ArcticShiftClient:
    """Small, rate-limit-aware client for Arctic Shift's comment archive."""

    BASE_URL = "https://arctic-shift.photon-reddit.com/api"

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 30.0),
    ) -> None:
        self.session = session or _retrying_session()
        self.timeout = timeout

    def get_user_comments(self, username: str, *, limit: int = 100) -> list[CommentRecord]:
        """Return up to ``limit`` newest archived comments for ``username``."""

        if not 1 <= limit <= 1_000:
            raise ValueError("Archive limit must be between 1 and 1,000.")

        results: list[CommentRecord] = []
        seen: set[str] = set()
        before: str | None = None

        while len(results) < limit:
            page_size = min(100, limit - len(results))
            params: dict[str, Any] = {
                "author": username,
                "limit": page_size,
                "sort": "desc",
            }
            if before:
                params["before"] = before

            payload = self._get("comments/search", params=params)
            items = _extract_items(payload)
            if not items:
                break

            page: list[CommentRecord] = []
            for item in items:
                try:
                    record = self._record_from_archive(item)
                except (KeyError, TypeError, ValueError):
                    continue
                if record.id in seen:
                    continue
                seen.add(record.id)
                page.append(record)

            if not page:
                break
            results.extend(page)

            if len(items) < page_size or len(results) >= limit:
                break

            oldest = min(record.created_utc for record in page)
            before = (oldest - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

        return sorted(results[:limit], key=lambda item: item.created_utc, reverse=True)

    def _get(self, endpoint: str, *, params: dict[str, Any]) -> Any:
        try:
            response = self.session.get(
                f"{self.BASE_URL}/{endpoint.lstrip('/')}",
                params=params,
                headers={"User-Agent": "ProfileLens/0.1 (portfolio visibility audit)"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise DataSourceError(f"Arctic Shift could not be reached: {exc}") from exc

        if response.status_code == 429:
            wait = response.headers.get("X-RateLimit-Reset", "an unspecified interval")
            raise DataSourceError(f"Arctic Shift rate limit reached; retry after {wait} seconds.")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise DataSourceError(f"Arctic Shift returned HTTP {response.status_code}.") from exc
        try:
            return response.json()
        except requests.JSONDecodeError as exc:
            raise DataSourceError("Arctic Shift returned an invalid JSON response.") from exc

    @staticmethod
    def _record_from_archive(item: dict[str, Any]) -> CommentRecord:
        return CommentRecord(
            id=item["id"],
            author=item.get("author") or "[unknown]",
            subreddit=item.get("subreddit") or "[unknown]",
            body=item.get("body") or "",
            created_utc=utc_datetime(item["created_utc"]),
            source=RecordSource.ARCTIC_SHIFT,
            permalink=item.get("permalink"),
            score=_optional_int(item.get("score")),
            link_id=item.get("link_id"),
        )


@dataclass(frozen=True, slots=True)
class RedditCredentials:
    """Approved read-only Reddit Data API configuration."""

    client_id: str
    client_secret: str
    user_agent: str

    @classmethod
    def from_environment(cls) -> RedditCredentials | None:
        approved = os.getenv("REDDIT_API_APPROVED", "false").strip().lower()
        if approved not in {"1", "true", "yes"}:
            return None
        values = {
            "client_id": os.getenv("REDDIT_CLIENT_ID", "").strip(),
            "client_secret": os.getenv("REDDIT_CLIENT_SECRET", "").strip(),
            "user_agent": os.getenv("REDDIT_USER_AGENT", "").strip(),
        }
        if not all(values.values()):
            raise ConfigurationError(
                "REDDIT_API_APPROVED is true, but one or more Reddit credentials are missing."
            )
        return cls(**values)


class RedditPublicClient:
    """Read-only PRAW adapter, enabled only for approved Reddit Data API use."""

    def __init__(self, credentials: RedditCredentials) -> None:
        try:
            import praw
        except ImportError as exc:  # pragma: no cover - installation problem
            raise ConfigurationError("Install PRAW to use live Reddit comparison.") from exc

        self._reddit = praw.Reddit(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            user_agent=credentials.user_agent,
            check_for_async=False,
        )

    def get_profile_comments(self, username: str, *, limit: int = 100) -> list[CommentRecord]:
        """Return comments exposed by Reddit's public user-comment listing."""

        if not 1 <= limit <= 1_000:
            raise ValueError("Public profile limit must be between 1 and 1,000.")
        try:
            listing: Iterable[Any] = self._reddit.redditor(username).comments.new(limit=limit)
            return [
                self._record_from_reddit(comment, RecordSource.REDDIT_PUBLIC_PROFILE)
                for comment in listing
            ]
        except Exception as exc:  # PRAW exposes several HTTP/auth exception classes
            raise DataSourceError(f"Reddit public-profile lookup failed: {exc}") from exc

    def probe_comment(self, comment_id: str) -> ProbeResult:
        """Check a comment ID directly to distinguish live, removed, and deleted states."""

        try:
            comment = self._reddit.comment(id=comment_id)
            comment.refresh()
            body = str(getattr(comment, "body", "") or "")
            author = getattr(comment, "author", None)

            if body == "[removed]":
                return ProbeResult(
                    CommentAvailability.REMOVED,
                    self._record_from_reddit(comment, RecordSource.REDDIT_DIRECT_LOOKUP),
                    "Reddit returned the moderator-removal marker.",
                )
            if body == "[deleted]" or (author is None and not body):
                return ProbeResult(
                    CommentAvailability.DELETED,
                    self._record_from_reddit(comment, RecordSource.REDDIT_DIRECT_LOOKUP),
                    "Reddit returned the user-deletion marker.",
                )
            return ProbeResult(
                CommentAvailability.LIVE,
                self._record_from_reddit(comment, RecordSource.REDDIT_DIRECT_LOOKUP),
                "The comment remains directly retrievable from Reddit.",
            )
        except Exception as exc:
            return ProbeResult(
                CommentAvailability.UNAVAILABLE,
                detail=f"Reddit did not return the comment: {type(exc).__name__}.",
            )

    @staticmethod
    def _record_from_reddit(comment: Any, source: RecordSource) -> CommentRecord:
        author_obj = getattr(comment, "author", None)
        subreddit_obj = getattr(comment, "subreddit", None)
        return CommentRecord(
            id=comment.id,
            author=str(author_obj) if author_obj is not None else "[deleted]",
            subreddit=str(subreddit_obj) if subreddit_obj is not None else "[unknown]",
            body=str(getattr(comment, "body", "") or ""),
            created_utc=utc_datetime(comment.created_utc),
            source=source,
            permalink=getattr(comment, "permalink", None),
            score=_optional_int(getattr(comment, "score", None)),
            link_id=getattr(comment, "link_id", None),
        )


def _retrying_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise DataSourceError("Arctic Shift returned an unexpected response structure.")


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
