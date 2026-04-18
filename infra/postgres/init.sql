-- =============================================================================
-- Code9 Analytics — postgres init
-- Загружается один раз при создании volume. Только расширения и ничего лишнего.
-- Схемы и таблицы создаются через alembic миграции (DB & Worker Engineer).
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;
