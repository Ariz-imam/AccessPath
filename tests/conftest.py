"""Shared pytest fixtures for isolated, deterministic API tests."""

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Give every test its own SQLite file so state cannot leak between tests."""
    from app import main

    test_db = tmp_path / "accesspath-test.db"
    monkeypatch.setattr(main, "DB_PATH", test_db)
    main.init_db()

    with TestClient(main.app) as test_client:
        yield test_client
