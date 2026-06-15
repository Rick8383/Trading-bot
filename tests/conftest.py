import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.core.config import load_config


@pytest.fixture
def settings():
    return load_config()
