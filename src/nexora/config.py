"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="NEXORA_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "production"
    data_dir: Path = Path("/data")
    library_dir: Path = Path("/library")
    log_level: str = "INFO"
    sqlite_busy_timeout_ms: int = 5_000
    session_cookie_secure: bool = True
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    media_public_base_url: str | None = None
    credential_key: SecretStr | None = None
    credential_key_file: Path | None = None
    credential_previous_keys: SecretStr | None = None
    credential_active_key_version: int = 1
    task_concurrency: int = 4
    task_poll_interval_ms: int = 250
    task_lease_seconds: int = 30
    metrics_sample_interval_seconds: int = 360
    shared_directory_roots: str = ""

    @field_validator("data_dir", "library_dir", mode="before")
    @classmethod
    def expand_path(cls, value: object) -> object:
        """Expand user markers without resolving non-existent paths."""

        if isinstance(value, str):
            return Path(value).expanduser()
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize and validate the configured log level."""

        normalized = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            msg = f"log_level must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return normalized

    @field_validator("media_public_base_url", mode="before")
    @classmethod
    def validate_media_public_base_url(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("media_public_base_url must be an HTTP(S) origin")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("media_public_base_url must be an HTTP(S) origin")
        return value.rstrip("/")

    @field_validator("task_concurrency")
    @classmethod
    def validate_task_concurrency(cls, value: int) -> int:
        if not 1 <= value <= 32:
            raise ValueError("task_concurrency must be between 1 and 32")
        return value

    @field_validator("task_poll_interval_ms")
    @classmethod
    def validate_task_poll_interval(cls, value: int) -> int:
        if not 10 <= value <= 60_000:
            raise ValueError("task_poll_interval_ms must be between 10 and 60000")
        return value

    @field_validator("task_lease_seconds")
    @classmethod
    def validate_task_lease(cls, value: int) -> int:
        if not 5 <= value <= 3_600:
            raise ValueError("task_lease_seconds must be between 5 and 3600")
        return value

    @field_validator("metrics_sample_interval_seconds")
    @classmethod
    def validate_metrics_interval(cls, value: int) -> int:
        if not 60 <= value <= 3_600:
            raise ValueError("metrics_sample_interval_seconds must be between 60 and 3600")
        return value

    @property
    def database_dir(self) -> Path:
        """Return the persistent database directory."""

        return self.data_dir / "database"

    @property
    def database_path(self) -> Path:
        """Return the primary SQLite database path."""

        return self.database_dir / "nexora.sqlite3"

    @property
    def trusted_host_list(self) -> list[str]:
        """Return normalized Host Header allowlist entries."""

        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def shared_directory_root_list(self) -> tuple[str, ...]:
        roots = tuple(
            value.strip() for value in self.shared_directory_roots.split(",") if value.strip()
        )
        if any(not value.startswith("/") or ".." in value.split("/") for value in roots):
            raise ValueError("shared_directory_roots contains an invalid path")
        return roots


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""

    return Settings()
