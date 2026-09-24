from profilelens.clients import ArcticShiftClient
from profilelens.models import RecordSource


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_arctic_shift_maps_and_sorts_comments():
    session = FakeSession(
        {
            "data": [
                {
                    "id": "older",
                    "author": "test_user",
                    "subreddit": "testing",
                    "body": "older body",
                    "created_utc": 1_700_000_000,
                    "permalink": "/r/testing/comments/post/title/older/",
                    "score": 2,
                },
                {
                    "id": "newer",
                    "author": "test_user",
                    "subreddit": "testing",
                    "body": "newer body",
                    "created_utc": 1_800_000_000,
                    "permalink": "/r/testing/comments/post/title/newer/",
                    "score": 3,
                },
            ]
        }
    )
    client = ArcticShiftClient(session=session)
    records = client.get_user_comments("test_user", limit=2)

    assert [record.id for record in records] == ["newer", "older"]
    assert all(record.source is RecordSource.ARCTIC_SHIFT for record in records)
    assert session.calls[0][1]["params"]["author"] == "test_user"
