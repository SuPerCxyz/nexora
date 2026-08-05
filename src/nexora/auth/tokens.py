"""Security token helpers."""

import hashlib


def digest_token(value: str) -> str:
    """Return a stable one-way token digest for database storage."""

    return hashlib.sha256(value.encode()).hexdigest()
