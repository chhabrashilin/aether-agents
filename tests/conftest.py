"""Shared pytest fixtures for ingest/db tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_agents.db.session import init_db, reset_engine_cache

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def cpcb_payload(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "cpcb_aqi_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def openaq_locations_payload(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "openaq_locations_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def openaq_measurements_payload(fixtures_dir: Path) -> dict:
    return json.loads(
        (fixtures_dir / "openaq_measurements_sample.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def sqlite_url(tmp_path) -> str:
    reset_engine_cache()
    url = f"sqlite:///{tmp_path / 'aether_test.db'}"
    init_db(url)
    yield url
    reset_engine_cache()
