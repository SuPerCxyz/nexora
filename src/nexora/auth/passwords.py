"""Password policy, hashing, and verification."""

import hmac

from pwdlib import PasswordHash

MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 1_024

_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash("nexora-dummy-password-never-used")


class PasswordPolicyError(ValueError):
    """Raised when a proposed password violates local policy."""


def validate_password(password: str, confirmation: str) -> None:
    """Validate password length and confirmation without logging inputs."""

    if not hmac.compare_digest(password, confirmation):
        raise PasswordPolicyError("两次输入的密码不一致")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"密码至少需要 {MINIMUM_PASSWORD_LENGTH} 个字符")
    if len(password) > MAXIMUM_PASSWORD_LENGTH:
        raise PasswordPolicyError("密码长度超过允许上限")


def hash_password(password: str) -> str:
    """Hash a validated password with the recommended Argon2 profile."""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password while preserving a dummy path for unknown users."""

    candidate_hash = password_hash or _dummy_hash
    verified = _password_hash.verify(password, candidate_hash)
    return password_hash is not None and verified
