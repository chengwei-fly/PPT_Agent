"""MinIO / S3 client (T021) + lifecycle policy for `ppt-cold`.

FR-009: 三类数据分离 (raw_files / parse_results / embeddings)
FR-026/FR-027: lifecycle policy transitions hot→cold after 180d
"""

from __future__ import annotations

import io
from datetime import timedelta
from typing import BinaryIO

from minio import Minio
from minio.lifecycleconfig import ExpirationRule, LifecycleConfig

from src.core.config import settings
from src.core.observability import get_logger

logger = get_logger("minio")

_client: Minio | None = None


def init_minio() -> None:
    global _client
    if _client is not None:
        return
    _client = Minio(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=settings.s3_secure,
        region=settings.s3_region,
    )
    _ensure_buckets()
    _set_lifecycle_policy()
    logger.info(
        "minio_initialized",
        endpoint=settings.s3_endpoint,
        hot=settings.s3_bucket_hot,
        cold=settings.s3_bucket_cold,
    )


def _ensure_buckets() -> None:
    assert _client is not None
    for bucket in (settings.s3_bucket_hot, settings.s3_bucket_cold):
        if not _client.bucket_exists(bucket):
            _client.make_bucket(bucket, location=settings.s3_region)
            logger.info("bucket_created", bucket=bucket)


def _set_lifecycle_policy() -> None:
    assert _client is not None
    rule = ExpirationRule(days=settings.task_retention_days + settings.task_purge_delay_days)
    config = LifecycleConfig([rule])
    try:
        _client.set_bucket_lifecycle(settings.s3_bucket_cold, config)
    except Exception as e:  # pragma: no cover
        logger.warning(f"lifecycle_policy_failed: {e}")


def get_minio() -> Minio:
    if _client is None:
        raise RuntimeError("MinIO not initialized — call init_minio() first")
    return _client


# ─── Helpers ────────────────────────────────────────────────────────
def put_object(
    bucket: str,
    key: str,
    data: bytes | BinaryIO,
    length: int | None = None,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> str:
    """Upload object. Returns the storage key (s3://bucket/key)."""
    client = get_minio()
    if isinstance(data, bytes):
        stream = io.BytesIO(data)
        length = length or len(data)
    else:
        stream = data
        length = length or 0
    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=stream,
        length=length,
        content_type=content_type,
        metadata=metadata or {},
    )
    return f"s3://{bucket}/{key}"


def get_object(bucket: str, key: str) -> bytes:
    client = get_minio()
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def remove_object(bucket: str, key: str) -> None:
    client = get_minio()
    client.remove_object(bucket, key)


def presign_url(bucket: str, key: str, expires: int = 3600) -> str:
    client = get_minio()
    return client.presigned_get_object(bucket, key, expires=timedelta(seconds=expires))


def presign_put_url(bucket: str, key: str, expires: int = 3600) -> str:
    client = get_minio()
    return client.presigned_put_object(bucket, key, expires=timedelta(seconds=expires))


# ─── Three-bucket organization (FR-009) ────────────────────────────
def raw_bucket() -> str:
    """原始文件 (raw_files) — immutable, lifecycle-managed."""
    return settings.s3_bucket_hot


def parse_bucket() -> str:
    """解析结果序列化（如 PDF 渲染、JSON dumps）."""
    return settings.s3_bucket_hot


def embed_bucket() -> str:
    """嵌入向量序列化（极少使用，留作 future export）."""
    return settings.s3_bucket_cold


def result_bucket() -> str:
    """生成结果 PPTX."""
    return settings.s3_bucket_hot
