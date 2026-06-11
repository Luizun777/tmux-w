"""Aísla los tests del estado real del usuario en %LOCALAPPDATA%\\tmuxw."""

import pytest

from tmuxw import paths


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    app = tmp_path / "tmuxw-test"
    monkeypatch.setattr(paths, "APP_DIR", app)
    monkeypatch.setattr(paths, "SERVER_FILE", app / "server.json")
    monkeypatch.setattr(paths, "LOG_FILE", app / "server.log")
    yield
