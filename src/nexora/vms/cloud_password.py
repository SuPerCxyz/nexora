"""One-way guest password hashing without persistent plaintext."""

import hmac
import subprocess

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1_024


def hash_guest_password(password: str, confirmation: str) -> str | None:
    if not password and not confirmation:
        return None
    if not hmac.compare_digest(password, confirmation):
        raise ValueError("cloud-init password confirmation does not match")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("cloud-init password length is invalid")
    try:
        result = subprocess.run(
            ("openssl", "passwd", "-6", "-stdin"),
            input=password.encode(),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("secure guest password hashing is unavailable") from exc
    digest = result.stdout.decode("ascii", errors="strict").strip()
    if result.returncode != 0 or not digest.startswith("$6$") or len(digest) > 256:
        raise ValueError("secure guest password hashing failed")
    return digest
