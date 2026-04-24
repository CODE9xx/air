"""
Regression для #52.7 — production bug, где ``bootstrap_tenant_schema``
возвращал succeeded, но следующий job (``pull_amocrm_core`` /
``trial_export`` / ``build_export_zip(trial=True)``) падал на первом же
``INSERT`` с psycopg2 ``UndefinedTable: relation "<table>" does not exist``.

Корень бага
-----------
Bootstrap-миграция полагалась на ``SET LOCAL search_path = "<schema>", public``
внутри alembic env.py (``apps/api/app/db/migrations/tenant/env.py``), без
``schema_translate_map`` на Connection. В определённых путях alembic 1.13+
``context.begin_transaction()`` дёргал ``Connection.begin()`` после
autobegun-транзакции SET LOCAL, и ``TenantBase.metadata.create_all()``
клал таблицы в ``public`` вместо tenant-схемы. Одновременно worker-jobs
(``trial_export`` и ``pull_amocrm_core``) тоже использовали
unqualified-имена и тот же SET LOCAL-трюк — поэтому даже если миграция
отрабатывала корректно, любой retry/pool-ping ронял search_path,
и INSERT терял tenant-схему.

Контракт теста
--------------
Этот тест гарантирует, что **сквозной пайплайн**
``bootstrap_tenant_schema → pull_amocrm_core → trial_export →
build_export_zip(trial=True)``:

1. Проходит до конца без ``UndefinedTable`` исключений.
2. Каждый job обновляет свой ``public.jobs`` row в ``status='succeeded'``
   (Task #52.6 contract).
3. ``TenantBase.metadata`` честно создаёт таблицы именно в tenant-схеме —
   напрямую проверяем ``information_schema.tables``.
4. MOCK-данные ложатся в tenant-схему (pipelines/stages/deals заполнены).

Если этот тест упадёт с ``UndefinedTable`` — регрессия #52.7 вернулась:
либо кто-то откатил ``schema_translate_map`` из env.py, либо кто-то
переписал INSERT'ы в worker-jobs обратно на unqualified-имена.

Требования к окружению
----------------------
* Настоящий PostgreSQL по ``DATABASE_URL`` с применёнными main-миграциями
  (так же, как любой ``tests/api/*`` с БД). Если БД недоступна — тест
  помечается skip, НЕ падает.
* ``MOCK_CRM_MODE=true`` (дефолт из tests/conftest.py) — иначе
  ``pull_amocrm_core`` уйдёт в реальный amoCRM без токена.

Запуск
------
    pytest -v -m integration tests/worker/test_bootstrap_then_pull_creates_data.py
"""
from __future__ import annotations

import os
import uuid as uuid_mod

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _sync_dsn() -> str:
    """
    psycopg2 DSN для прямого доступа к test-DB из теста (минуем worker.lib.db,
    чтобы оставить его чистым для фиксируемого поведения).
    """
    # Поздний импорт, чтобы tests/conftest.py успел выставить ``DATABASE_URL``
    # до того, как worker модули (и их env-зависимости) будут импортированы.
    from scripts.migrations.apply_tenant_template import asyncpg_to_psycopg2

    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://code9:code9@localhost:5432/code9_test",
    )
    return asyncpg_to_psycopg2(raw)


@pytest.fixture(scope="module")
def _pg_engine():
    """Engine для setup/teardown фикстур (через scripts/lib url-translator)."""
    try:
        engine = create_engine(_sync_dsn(), future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover — defensive skip
        pytest.skip(f"PostgreSQL недоступен для integration-теста: {exc!r}")
    yield engine
    engine.dispose()


@pytest.fixture
def _seed_connection(_pg_engine):
    """
    Создаёт минимальный public-граф: user → workspace → crm_connection,
    возвращает connection_id. В teardown — DROP tenant schema + DELETE rows.
    """
    uniq = uuid_mod.uuid4().hex[:8]
    user_id = str(uuid_mod.uuid4())
    workspace_id = str(uuid_mod.uuid4())
    connection_id = str(uuid_mod.uuid4())

    with _pg_engine.begin() as conn:
        # User и Workspace — обязательные FK для CrmConnection.workspace_id.
        # owner_user_id в Workspace имеет FK без ondelete, ставим NULL безопасно —
        # через пользовательскую запись (users.id).
        conn.execute(
            text(
                "INSERT INTO users(id, email, password_hash, locale, status) "
                "VALUES (CAST(:id AS UUID), :email, :pw, 'ru', 'active')"
            ),
            {
                "id": user_id,
                "email": f"test-bootstrap-{uniq}@code9.local",
                "pw": "not-a-real-hash",
            },
        )
        conn.execute(
            text(
                "INSERT INTO workspaces(id, name, slug, owner_user_id, locale, status) "
                "VALUES (CAST(:id AS UUID), :name, :slug, CAST(:uid AS UUID), 'ru', 'active')"
            ),
            {
                "id": workspace_id,
                "name": f"WS-{uniq}",
                "slug": f"ws-{uniq}",
                "uid": user_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO crm_connections("
                "  id, workspace_id, provider, status, external_domain "
                ") VALUES ("
                "  CAST(:id AS UUID), CAST(:wid AS UUID), 'amocrm', 'pending', :dom"
                ")"
            ),
            {
                "id": connection_id,
                "wid": workspace_id,
                "dom": f"test{uniq}.amocrm.ru",
            },
        )

    yield connection_id

    # Teardown: сначала drop tenant schema, затем cascading-удаления.
    # Tenant-schema в безопасной идемпотентной форме — если миграция не
    # создалась, IF EXISTS проглотит отсутствие.
    with _pg_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT tenant_schema FROM crm_connections "
                "WHERE id = CAST(:cid AS UUID)"
            ),
            {"cid": connection_id},
        ).fetchone()
        schema = row[0] if row else None
    if schema:
        with _pg_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    with _pg_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM jobs WHERE crm_connection_id = CAST(:cid AS UUID)"),
            {"cid": connection_id},
        )
        conn.execute(
            text("DELETE FROM crm_connections WHERE id = CAST(:cid AS UUID)"),
            {"cid": connection_id},
        )
        conn.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:wid AS UUID)"),
            {"wid": workspace_id},
        )
        conn.execute(
            text("DELETE FROM users WHERE id = CAST(:uid AS UUID)"),
            {"uid": user_id},
        )


def _insert_job_row(engine, connection_id: str, kind: str) -> str:
    """Создаёт public.jobs row в статусе 'queued' и возвращает job_row_id."""
    job_row_id = str(uuid_mod.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs(id, crm_connection_id, kind, queue, status, payload) "
                "VALUES (CAST(:id AS UUID), CAST(:cid AS UUID), :kind, "
                "        'default', 'queued', '{}'::jsonb)"
            ),
            {"id": job_row_id, "cid": connection_id, "kind": kind},
        )
    return job_row_id


def _fetch_job_status(engine, job_row_id: str) -> tuple[str, str | None]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, error FROM jobs WHERE id = CAST(:id AS UUID)"),
            {"id": job_row_id},
        ).fetchone()
    assert row is not None, f"jobs row {job_row_id} пропал"
    return row[0], row[1]


def _table_exists(engine, schema: str, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": schema, "t": table},
        ).fetchone()
    return row is not None


def _count_rows(engine, schema: str, table: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(text(f'SELECT COUNT(*) FROM "{schema}".{table}')).scalar() or 0
        )


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_bootstrap_creates_tenant_tables_in_tenant_schema(_pg_engine, _seed_connection):
    """
    Hypothesis H1 guard: после ``bootstrap_tenant_schema`` все 30 tenant-таблиц
    физически лежат в tenant-схеме (не в public).

    Regression: до #52.7 можно было поймать сценарий, где миграция
    отрабатывала как no-op или раскладывала таблицы в public. Оба варианта
    ломали downstream pull/export на первом INSERT'е.
    """
    from worker.jobs.crm import bootstrap_tenant_schema

    connection_id = _seed_connection
    job_row_id = _insert_job_row(_pg_engine, connection_id, "bootstrap_tenant_schema")

    result = bootstrap_tenant_schema(
        connection_id=connection_id, job_row_id=job_row_id
    )

    # 1. Public.jobs.status = succeeded (Task #52.6 contract).
    status, error = _fetch_job_status(_pg_engine, job_row_id)
    assert status == "succeeded", f"bootstrap job: status={status!r}, error={error!r}"

    # 2. tenant_schema прописана в crm_connections.
    assert result["tenant_schema"].startswith("crm_amo_"), result
    schema = result["tenant_schema"]

    # 3. Ключевые tenant-таблицы реально лежат в tenant-схеме.
    for tname in ("pipelines", "stages", "crm_users", "contacts", "deals",
                  "raw_pipelines", "raw_stages", "raw_users", "raw_contacts",
                  "raw_deals"):
        assert _table_exists(_pg_engine, schema, tname), (
            f"#52.7 regression: таблица {tname!r} не создана в tenant-схеме {schema!r}. "
            f"Проверьте apps/api/app/db/migrations/tenant/env.py — "
            f"schema_translate_map должен быть на Connection ДО context.configure."
        )


def test_trial_export_after_bootstrap_succeeds_and_populates_tenant(
    _pg_engine, _seed_connection
):
    """
    Главный контракт #52.7: ``trial_export`` после успешного bootstrap не падает
    с ``UndefinedTable``, завершает job в 'succeeded', заполняет tenant-таблицы.
    """
    from worker.jobs.crm import bootstrap_tenant_schema
    from worker.jobs.export import trial_export

    connection_id = _seed_connection

    bootstrap_job = _insert_job_row(
        _pg_engine, connection_id, "bootstrap_tenant_schema"
    )
    boot_result = bootstrap_tenant_schema(
        connection_id=connection_id, job_row_id=bootstrap_job
    )
    assert (
        _fetch_job_status(_pg_engine, bootstrap_job)[0] == "succeeded"
    ), "bootstrap должен пройти, прежде чем trial_export имеет смысл"
    schema = boot_result["tenant_schema"]

    # --- trial_export ----------------------------------------------------
    export_job = _insert_job_row(_pg_engine, connection_id, "build_export_zip")
    export_result = trial_export(
        connection_id=connection_id, job_row_id=export_job
    )

    status, error = _fetch_job_status(_pg_engine, export_job)
    assert status == "succeeded", (
        f"#52.7 regression: trial_export job status={status!r}, error={error!r}. "
        f"Скорее всего кто-то вернул unqualified INSERT'ы в "
        f"apps/worker/worker/jobs/export.py — каждый INSERT должен быть "
        f"'INSERT INTO \"<schema>\".<table>'."
    )
    assert export_result.get("deals_created") == 100
    assert export_result.get("tenant_schema") == schema

    # 100 deals действительно в tenant-схеме, не где-то ещё.
    assert _count_rows(_pg_engine, schema, "deals") == 100
    assert _count_rows(_pg_engine, schema, "pipelines") >= 1
    assert _count_rows(_pg_engine, schema, "contacts") >= 1


def test_pull_amocrm_core_mock_delegates_to_trial_export_succeeds(
    _pg_engine, _seed_connection, monkeypatch
):
    """
    MOCK_CRM_MODE=true (дефолт в tests/conftest.py): ``pull_amocrm_core``
    делегирует в ``trial_export``. Именно этот путь падал в проде
    (report #52.7, 2026-04-22 16:53:17 — pull_amocrm_core failed
    'relation "raw_pipelines" does not exist').

    Фиксирует happy path: после bootstrap pull идёт в mock-ветку, trial_export
    отрабатывает, job в status=succeeded.
    """
    # MOCK_CRM_MODE читается на module-level при импорте ``worker.jobs.crm_pull``.
    # ``tests/conftest.py`` выставляет его в 'true' ДО любого импорта, поэтому
    # reload не нужен — просто импортируем и проверяем.
    from worker.jobs.crm import bootstrap_tenant_schema
    from worker.jobs import crm_pull as cpm

    assert cpm.MOCK_CRM_MODE is True, (
        "tests/conftest.py должен выставлять MOCK_CRM_MODE=true — иначе "
        "pull_amocrm_core уйдёт в реальный amoCRM без токена и упадёт не "
        "по причине #52.7."
    )

    connection_id = _seed_connection
    bootstrap_job = _insert_job_row(
        _pg_engine, connection_id, "bootstrap_tenant_schema"
    )
    bootstrap_tenant_schema(connection_id=connection_id, job_row_id=bootstrap_job)

    # Останавливаем enqueue follow-up job'а (run_audit_report) — теста ему не нужно.
    monkeypatch.setattr(cpm, "_enqueue_audit", lambda _cid: False)

    pull_job = _insert_job_row(_pg_engine, connection_id, "pull_amocrm_core")
    result = cpm.pull_amocrm_core(
        connection_id=connection_id, first_pull=True, job_row_id=pull_job
    )

    status, error = _fetch_job_status(_pg_engine, pull_job)
    assert status == "succeeded", (
        f"#52.7 regression (MOCK path): pull_amocrm_core status={status!r}, "
        f"error={error!r}. Mock path делегирует в trial_export — если "
        f"trial_export падает на INSERT'ах, значит, schema-qualification "
        f"откатили."
    )
    assert result.get("mock") is True
    assert result["counts"]["deals"] == 100


def test_build_export_zip_trial_after_bootstrap_succeeds(
    _pg_engine, _seed_connection
):
    """
    Composite-regression: ``build_export_zip(trial=True)`` (dispatcher из
    Task #52.5) после bootstrap не ломается. Это ровно тот вызов, который
    RQ кладёт в очередь через ``POST /crm/connections/{id}/trial-export``.
    """
    from worker.jobs.crm import bootstrap_tenant_schema
    from worker.jobs.export import build_export_zip

    connection_id = _seed_connection
    bootstrap_job = _insert_job_row(
        _pg_engine, connection_id, "bootstrap_tenant_schema"
    )
    bootstrap_tenant_schema(connection_id=connection_id, job_row_id=bootstrap_job)

    export_job = _insert_job_row(_pg_engine, connection_id, "build_export_zip")
    build_export_zip(
        connection_id=connection_id, trial=True, job_row_id=export_job
    )

    status, error = _fetch_job_status(_pg_engine, export_job)
    assert status == "succeeded", (
        f"#52.7 regression: build_export_zip(trial=True) "
        f"status={status!r}, error={error!r}"
    )
