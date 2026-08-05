from pathlib import Path

import pytest
from pydantic import ValidationError

from nexora.config import Settings


def test_settings_use_nexora_environment_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXORA_DATA_DIR", "/tmp/nexora-test-data")
    monkeypatch.setenv("NEXORA_LOG_LEVEL", "debug")

    settings = Settings(_env_file=None)

    assert Path("/tmp/nexora-test-data") == settings.data_dir
    assert "DEBUG" == settings.log_level


def test_settings_reject_unknown_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="verbose", _env_file=None)


def test_database_path_is_scoped_to_data_dir() -> None:
    settings = Settings(data_dir="/srv/nexora", _env_file=None)

    assert Path("/srv/nexora/database") == settings.database_dir
    assert Path("/srv/nexora/database/nexora.sqlite3") == settings.database_path


def test_media_public_base_url_requires_origin_without_credentials() -> None:
    settings = Settings(
        media_public_base_url="https://nexora.example.test:8443/",
        _env_file=None,
    )
    assert "https://nexora.example.test:8443" == settings.media_public_base_url

    with pytest.raises(ValidationError):
        Settings(
            media_public_base_url="https://user:secret@example.test/media?token=x",
            _env_file=None,
        )
