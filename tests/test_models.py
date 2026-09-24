from datetime import UTC, datetime

from profilelens.models import CommentRecord, RecordSource, normalize_comment_id, utc_datetime


def test_normalize_comment_id_removes_prefix():
    assert normalize_comment_id("t1_abc123") == "abc123"


def test_utc_datetime_accepts_epoch_and_iso():
    assert utc_datetime(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert utc_datetime("2026-09-20T12:00:00Z").tzinfo == UTC


def test_comment_record_builds_absolute_reddit_url():
    record = CommentRecord(
        id="abc123",
        author="tester",
        subreddit="python",
        body="hello",
        created_utc="2026-09-20T12:00:00Z",
        source=RecordSource.ARCTIC_SHIFT,
        permalink="/r/python/comments/post/title/abc123/",
    )
    assert record.reddit_url == "https://www.reddit.com/r/python/comments/post/title/abc123/"
    assert record.to_dict(include_body=False)["body"] == "hello"
