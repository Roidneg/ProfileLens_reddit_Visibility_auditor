"""Profile input parsing and validation."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse


class ProfileInputError(ValueError):
    """Raised when a Reddit username cannot be safely extracted."""


_USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
_ALLOWED_HOSTS = {
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "new.reddit.com",
    "m.reddit.com",
}


def extract_username(profile_input: str) -> str:
    """Extract a username from a Reddit URL, ``u/name`` form, or plain name."""

    candidate = str(profile_input or "").strip()
    if not candidate:
        raise ProfileInputError("Enter a Reddit profile URL or username.")

    if "://" in candidate:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            raise ProfileInputError("The profile URL must use a reddit.com hostname.")
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        lowered = [part.lower() for part in parts]
        username = ""
        for marker in ("user", "u"):
            if marker in lowered:
                index = lowered.index(marker)
                if index + 1 < len(parts):
                    username = parts[index + 1]
                    break
        if not username:
            raise ProfileInputError("The URL does not contain a Reddit user profile.")
    else:
        username = candidate
        if username.startswith("@"):
            username = username[1:]
        if username.lower().startswith("u/"):
            username = username[2:]
        username = username.strip("/")

    if username.lower() in {"me", "deleted", "[deleted]"}:
        raise ProfileInputError("Enter a specific, active Reddit username.")
    if not _USERNAME.fullmatch(username):
        raise ProfileInputError(
            "Reddit usernames may contain letters, numbers, underscores, and hyphens."
        )
    return username
