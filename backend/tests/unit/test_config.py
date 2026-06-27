"""Unit tests for configuration layer (T013)."""

from __future__ import annotations

import pytest


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Minimum env vars to instantiate Settings without touching .env."""
    env: dict[str, str] = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "DATABASE_URL_SYNC": "postgresql://u:p@localhost:5432/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "S3_ENDPOINT": "localhost:9000",
        "S3_ACCESS_KEY": "x",
        "S3_SECRET_KEY": "x",
        "SECRET_KEY": "x" * 32,
        "OPENAI_API_KEY": "sk-replace",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


class TestSettings:
    def test_defaults_load(self, base_env: dict[str, str]) -> None:
        # Reset cached settings
        from src.core import config as cfg_mod

        cfg_mod.get_settings.cache_clear()
        s = cfg_mod.get_settings()
        assert s.app_env == "test"
        assert s.queue_deadline_seconds == 300
        assert s.rate_limit_per_min == 60
        assert s.user_concurrency_limit == 2
        assert s.embedding_dimension == 1536
        assert s.generation_timeout_seconds == 300

    def test_cors_origins_parsed(self, base_env: dict[str, str]) -> None:
        from src.core import config as cfg_mod

        cfg_mod.get_settings.cache_clear()
        s = cfg_mod.get_settings()
        origins = s.cors_allow_origins_list
        assert isinstance(origins, list)
        assert "http://localhost:5173" in origins

    def test_is_production_flag(self, base_env: dict[str, str]) -> None:
        from src.core import config as cfg_mod

        cfg_mod.get_settings.cache_clear()
        s = cfg_mod.get_settings()
        assert s.is_production is False
        assert s.is_test is True

    def test_pii_fields_parsed(self, base_env: dict[str, str]) -> None:
        from src.core import config as cfg_mod

        cfg_mod.get_settings.cache_clear()
        s = cfg_mod.get_settings()
        assert "phone" in s.pii_fields
        assert "email" in s.pii_fields
        assert "id_card" in s.pii_fields

    def test_secret_key_min_length_enforced(self, base_env: dict[str, str]) -> None:
        from pydantic import ValidationError

        from src.core import config as cfg_mod

        cfg_mod.get_settings.cache_clear()
        with pytest.raises(ValidationError):
            cfg_mod.Settings(secret_key="too-short")  # type: ignore[call-arg]
