import pytest

from nexora.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password,
    verify_password,
)


def test_password_hash_uses_argon2_and_verifies() -> None:
    password = "a-long-development-password"

    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2")
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_unknown_user_uses_dummy_verification_path() -> None:
    assert verify_password("unknown-password", None) is False


@pytest.mark.parametrize(
    ("password", "confirmation"),
    [
        ("short", "short"),
        ("1234567", "1234567"),
        ("a-valid-password", "a-different-password"),
    ],
)
def test_password_policy_rejects_invalid_input(
    password: str,
    confirmation: str,
) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password(password, confirmation)


def test_password_policy_accepts_matching_long_password() -> None:
    password = "a-valid-password"

    validate_password(password, password)


def test_password_policy_accepts_exact_minimum_length() -> None:
    password = "12345678"

    validate_password(password, password)
