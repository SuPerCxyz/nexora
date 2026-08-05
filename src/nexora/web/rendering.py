"""Jinja template configuration."""

import os
from pathlib import Path

from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(os.environ.get("NEXORA_PROJECT_ROOT", Path(__file__).resolve().parents[3]))
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")
