"""Unit tests for GET /api/playbooks/ — no DB, no LLM calls."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.playbooks as playbooks_module


def _write_playbook(directory: Path, content: str) -> None:
    (directory / "test.yaml").write_text(content)


SAMPLE_YAML = """\
id: test-playbook-v1
name: Test Playbook
version: "2.0"
description: A test playbook
rules:
  - category: governing_law
    condition: eq
    required_value: "California"
    severity: high
  - category: confidentiality
    condition: present
    severity: medium
"""


def test_list_playbooks_returns_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_playbook(Path(tmpdir), SAMPLE_YAML)

        # Patch get_settings so the router uses our temp dir
        from app.config import Settings
        fake_settings = Settings.model_construct(
            playbooks_dir=tmpdir,
            anthropic_api_key="x",
            voyage_api_key="x",
            cohere_api_key="x",
        )
        monkeypatch.setattr(playbooks_module, "get_settings", lambda: fake_settings)

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(playbooks_module.router, prefix="/api/playbooks")

        client = TestClient(app)
        resp = client.get("/api/playbooks/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        pb = data[0]
        assert pb["id"] == "test-playbook-v1"
        assert pb["name"] == "Test Playbook"
        assert pb["version"] == "2.0"
        assert pb["rule_count"] == 2
        assert "rules" not in pb  # must not leak rule details


def test_list_playbooks_empty_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from app.config import Settings
        fake_settings = Settings.model_construct(
            playbooks_dir=tmpdir,
            anthropic_api_key="x",
            voyage_api_key="x",
            cohere_api_key="x",
        )
        monkeypatch.setattr(playbooks_module, "get_settings", lambda: fake_settings)

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(playbooks_module.router, prefix="/api/playbooks")

        client = TestClient(app)
        resp = client.get("/api/playbooks/")
        assert resp.status_code == 200
        assert resp.json() == []
