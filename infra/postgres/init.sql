-- PPTagent Postgres init: required extensions only.
-- Schema migrations live in backend/migrations/versions/*.py (Alembic).
-- This file is mounted to /docker-entrypoint-initdb.d/ for fresh volumes.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- trigram for fuzzy text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";     -- GIN index support
