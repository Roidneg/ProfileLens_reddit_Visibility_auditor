import pytest

from profilelens.parsing import ProfileInputError, extract_username


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Reasonable_Way6181", "Reasonable_Way6181"),
        ("u/Reasonable_Way6181", "Reasonable_Way6181"),
        ("@Reasonable_Way6181", "Reasonable_Way6181"),
        (
            "https://www.reddit.com/user/Reasonable_Way6181/comments/",
            "Reasonable_Way6181",
        ),
        ("https://old.reddit.com/u/test-user/", "test-user"),
    ],
)
def test_extract_username(value, expected):
    assert extract_username(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.com/user/test_user/",
        "https://www.reddit.com/r/python/",
        "u/me",
        "bad user name",
    ],
)
def test_extract_username_rejects_invalid_input(value):
    with pytest.raises(ProfileInputError):
        extract_username(value)
