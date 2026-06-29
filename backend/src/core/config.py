"""Pydantic v2 Settings (env-driven) per T013."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — loaded from environment / .env file.

    All fields MUST be lowercase + underscore. Use Field(description=...) for OpenAPI.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Allow nested env vars like DATABASE_URL or REDIS_URL
        env_parse_none_str="null",
    )

    # ── App ────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "test", "production"] = "development"
    app_name: str = "pptagent-backend"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_namespace: str = "pptagent"

    # ── Database ───────────────────────────────────────────────────
    database_url: PostgresDsn
    database_url_sync: str
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False

    # ── Redis ──────────────────────────────────────────────────────
    redis_url: RedisDsn
    queue_deadline_seconds: int = 300  # FR-029: 5min queue timeout
    rate_limit_per_min: int = 60
    user_concurrency_limit: int = 2  # FR-029

    # ── S3 / MinIO (FR-009 三类数据分离) ──────────────────────────
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_hot: str = "ppt-hot"
    s3_bucket_cold: str = "ppt-cold"
    s3_secure: bool = False
    s3_region: str = "us-east-1"

    # ── OpenTelemetry ──────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "pptagent-backend"
    otel_traces_sampler: str = "parentbased_traceidratio"
    otel_traces_sampler_arg: float = 1.0

    # ── Security / API Keys (Constitution §IV) ─────────────────────
    secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    pii_fields: list[str] = Field(
        default_factory=lambda: [
            "phone",
            "email",
            "id_card",
            "customer_name",
            "address",
            "bank_card",
        ]
    )
    pii_detection_lang: str = "zh"

    # ── Generation ─────────────────────────────────────────────────
    generation_timeout_seconds: int = 300  # SC-001
    generation_max_concurrency_per_user: int = 2
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    embedding_provider: Literal["openai", "local"] = "openai"
    openai_api_key: str = "sk-replace"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2

    # ── CORS ───────────────────────────────────────────────────────
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"
    cors_allow_credentials: bool = True

    # ── Retention (FR-026/FR-027) ─────────────────────────────────
    task_retention_days: int = 180
    task_notify_before_days: int = 14
    task_purge_delay_days: int = 7
    sample_retention_days: int = 0  # 0 = forever

    # ── Dev ────────────────────────────────────────────────────────
    dev_api_key: str = "dev-key"
    dev_user_email: str = "dev@pptagent.local"

    # ── Curated material library (US6 / system-curated extension) ──
    # When enabled, the importer writes orphan ``slide_assets`` rows
    # (source_sample_id IS NULL) that are visible to every user with
    # ``include_orphan=true``. Disabling is purely a safety switch —
    # the importer script will still run, but rows are tagged with
    # ``metadata_json.curated=false`` instead.
    curated_library_enabled: bool = True
    # Hard cap on how many curated assets one run can insert. Set to 0
    # for unlimited. Protects the DB when running on huge source trees.
    curated_library_max_assets_per_run: int = 0
    # When True the import CLI / admin API will prefer multimodal LLM
    # classification if an LLM key is configured.
    curated_library_use_llm: bool = False
    # Optional override for the multimodal model (e.g. qwen-vl-max).
    # Defaults to ``llm_model`` when empty.
    curated_library_multimodal_model: str = ""

    # ── Derived helpers ────────────────────────────────────────────
    @field_validator("cors_allow_origins")
    @classmethod
    def _validate_cors(cls, v: str) -> str:
        if not v:
            raise ValueError("cors_allow_origins must not be empty")
        return v

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
