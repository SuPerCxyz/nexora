from base64 import b64encode
from pathlib import Path

import pytest

from nexora.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Provide isolated runtime paths for each test."""

    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        library_dir=tmp_path / "library",
        session_cookie_secure=False,
        credential_key=b64encode(b"t" * 32).decode(),
        _env_file=None,
    )
