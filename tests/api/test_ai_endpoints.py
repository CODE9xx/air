"""
Контрактные тесты ``app.ai.router`` ↔ ``worker.jobs.ai.analyze_conversation``.

Bug (router↔worker signature mismatch, предшествует Task #52.6)
---------------------------------------------------------------
Router-хэндлер ``ai_analyze`` формировал ``worker_payload`` без ключа
``workspace_id``. Worker-функция::

    def analyze_conversation(
        workspace_id: str,              # REQUIRED positional
        *,
        connection_id: str | None = None,
        kind: str = "call_transcript",
        job_row_id: str | None = None,
    ) -> dict[str, Any]: ...

``enqueue()`` распаковывает payload как ``kwargs`` (Bug D fix
Task #52.3D), а не позиционно — поэтому отсутствие ``workspace_id``
в payload даёт::

    TypeError: analyze_conversation() missing 1 required positional
    argument: 'workspace_id'

на worker pickup. Баг предшествует Task #52.6 и не воспроизводился
в live-прогоне (RQ pickup для ``ai``-очереди не был задействован),
но обнаружен при аудите enqueue-callers в рамках #52.6.

Фикс: ``ai_analyze`` добавляет ``workspace_id`` в ``worker_payload``
(берётся из ``conn.workspace_id``, уже резолвится в ``_resolve_conn``).
``job_row_id`` продолжает плыть через ``enqueue(..., job_row_id=...)``
(контракт #52.6 не тронут).

Что покрывают тесты
-------------------
1. **Signature lock**: все REQUIRED (без default) параметры
   ``analyze_conversation`` — это kwargs, которые router обязан
   положить в payload. ``job_row_id`` добавляется ``enqueue()``,
   поэтому он в payload быть не должен.
2. **Router payload shape**: прямой вызов ``ai_analyze`` handler'а
   с замоканными session/user/enqueue — в пойманном payload
   присутствуют все required-ключи из worker-сигнатуры.
3. **Regression guard — workspace_id в payload**: явная проверка,
   что ``workspace_id`` попал в worker_payload (а не только в
   ``job.workspace_id`` DB-колонку).
4. **Stored payload (public.jobs.payload) не содержит workspace_id**:
   стабильность контракта DB vs wire — workspace_id уже есть в
   ``jobs.workspace_id`` FK-колонке, дублировать в JSONB-payload
   не нужно.

Безопасность теста
------------------
Не использует реальные creds, БД, Redis. Только in-memory моки —
запускается через ``pytest tests/api/test_ai_endpoints.py`` в любом
окружении, где есть доступ к исходникам ``apps/api`` и ``apps/worker``.
"""
from __future__ import annotations

import inspect
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Worker-пакет живёт в ``apps/worker/``. В PYTHONPATH api-контейнера
# его нет по умолчанию — добавляем явно (тот же приём, что и в
# ``test_amocrm_worker_credentials.py`` / ``test_crm_pull_metadata_sql_column.py``).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_SRC = _REPO_ROOT / "apps" / "worker"
if _WORKER_SRC.is_dir() and str(_WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKER_SRC))

from worker.jobs.ai import analyze_conversation  # noqa: E402  (sys.path hack)

from app.ai.router import ai_analyze  # noqa: E402


def _required_worker_kwargs(func) -> set[str]:
    """Имена параметров без default — их обязан предоставить вызывающий.

    Исключаем ``*args`` / ``**kwargs`` (varargs) — они не «обязательные
    по имени».
    """
    sig = inspect.signature(func)
    return {
        name
        for name, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty
        and p.kind
        not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    }


# ---------------------------------------------------------------------------
# 1. Signature lock: заморозка required-параметров worker-функции.
# ---------------------------------------------------------------------------


def test_analyze_conversation_required_kwargs_lock():
    """
    Если в ``analyze_conversation`` появится новый REQUIRED параметр —
    этот тест упадёт первым, сигнализируя: нужно обновить router (или
    сделать параметр опциональным).

    Жёсткое равенство (а не ``<=``) намеренно: добавление нового required
    kwarg без обновления router — регрессия той же природы, что и
    отсутствие ``workspace_id``.
    """
    required = _required_worker_kwargs(analyze_conversation)
    assert required == {"workspace_id"}, (
        f"Required kwargs of analyze_conversation() changed to {required!r}. "
        "Router в apps/api/app/ai/router.py:ai_analyze должен класть "
        "эти ключи в worker_payload. "
        "Либо сделай новые параметры опциональными (с default), либо "
        "добавь их в worker_payload и обнови этот тест."
    )


# ---------------------------------------------------------------------------
# 2/3. Router payload включает все required worker kwargs.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_analyze_router_payload_satisfies_worker_signature():
    """
    Интеграционный контракт: когда router помещает job в очередь,
    передаваемый ``enqueue()`` payload покрывает все REQUIRED параметры
    ``analyze_conversation``.

    Не требует БД/Redis — мокаем ``_resolve_conn`` и ``enqueue``.
    Ключевое: именно тот dict, который router передаёт в enqueue(),
    должен содержать все required worker kwargs.
    """
    workspace_id = uuid.UUID("1ede9725-4b4e-4157-8a12-a8ac9c67f274")
    conn_id = uuid.UUID("2ede9725-4b4e-4157-8a12-a8ac9c67f274")

    fake_conn = MagicMock()
    fake_conn.id = conn_id
    fake_conn.workspace_id = workspace_id

    fake_user = MagicMock()

    # session.add должен симулировать server_default gen_random_uuid():
    # после .flush() у Job появляется .id. Эмулируем заранее в add().
    def _set_id_on_add(obj):
        obj.id = uuid.uuid4()

    fake_session = MagicMock()
    fake_session.add = MagicMock(side_effect=_set_id_on_add)
    fake_session.flush = AsyncMock()
    fake_session.commit = AsyncMock()

    captured: dict = {}

    def fake_enqueue(kind, payload, *, depends_on=None, job_row_id=None):
        captured["kind"] = kind
        captured["payload"] = dict(payload)  # snapshot — защищаемся от мутации
        captured["job_row_id"] = job_row_id
        return "fake-rq-id-aiendpoint"

    with (
        patch(
            "app.ai.router._resolve_conn",
            new=AsyncMock(return_value=fake_conn),
        ),
        patch("app.ai.router.enqueue", side_effect=fake_enqueue),
    ):
        result = await ai_analyze(
            connection_id=conn_id,
            user=fake_user,
            session=fake_session,
        )

    # Router должен был поставить job в очередь.
    assert captured.get("kind") == "analyze_conversation", (
        f"ai_analyze должен ставить job kind='analyze_conversation', "
        f"получили {captured.get('kind')!r}"
    )

    # Task #52.6: job_row_id передаётся отдельным kwarg в enqueue(),
    # не частью payload.
    assert captured["job_row_id"] is not None, (
        "Task #52.6 regression: ai_analyze перестал передавать job_row_id "
        "в enqueue() — public.jobs.status останется 'queued' навсегда."
    )
    assert "job_row_id" not in captured["payload"], (
        "job_row_id не должен дублироваться в worker_payload — "
        "enqueue() сам добавляет его в worker kwargs."
    )

    # Главный контракт теста: payload покрывает required worker params.
    required = _required_worker_kwargs(analyze_conversation)
    missing = required - captured["payload"].keys()
    assert not missing, (
        f"Router↔worker signature mismatch: worker_payload missing "
        f"{missing!r}. analyze_conversation() требует {required!r} как "
        f"REQUIRED, got payload keys {set(captured['payload'].keys())!r}. "
        "Добавь отсутствующие ключи в worker_payload в ai_analyze handler."
    )

    # Явно: workspace_id в payload и равен conn.workspace_id.
    assert captured["payload"].get("workspace_id") == str(workspace_id), (
        f"workspace_id в worker_payload должен быть str(conn.workspace_id), "
        f"получили {captured['payload'].get('workspace_id')!r}"
    )
    # connection_id тоже должен остаться.
    assert captured["payload"].get("connection_id") == str(conn_id)

    # Router возвращает job_id (UUID строкой).
    assert "job_id" in result
    uuid.UUID(result["job_id"])  # не кидает — значит валидный UUID


# ---------------------------------------------------------------------------
# 4. Stored payload (public.jobs.payload) НЕ содержит workspace_id.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_analyze_stored_payload_does_not_duplicate_workspace_id():
    """
    ``public.jobs.workspace_id`` — FK-колонка, source of truth для
    workspace привязки. Дублировать workspace_id в ``public.jobs.payload``
    (JSONB) — лишнее: при ручном UPDATE workspace_id рассинхрон между
    колонкой и JSONB неизбежен.

    Worker_payload (который идёт в RQ) workspace_id содержит —
    это проверяется в тесте выше. А stored payload (public.jobs.payload)
    — нет.
    """
    workspace_id = uuid.UUID("1ede9725-4b4e-4157-8a12-a8ac9c67f274")
    conn_id = uuid.UUID("2ede9725-4b4e-4157-8a12-a8ac9c67f274")

    fake_conn = MagicMock()
    fake_conn.id = conn_id
    fake_conn.workspace_id = workspace_id
    fake_user = MagicMock()

    captured_jobs: list = []

    def _capture_add(obj):
        captured_jobs.append(obj)
        obj.id = uuid.uuid4()

    fake_session = MagicMock()
    fake_session.add = MagicMock(side_effect=_capture_add)
    fake_session.flush = AsyncMock()
    fake_session.commit = AsyncMock()

    with (
        patch(
            "app.ai.router._resolve_conn",
            new=AsyncMock(return_value=fake_conn),
        ),
        patch("app.ai.router.enqueue", return_value="fake-rq-id"),
    ):
        await ai_analyze(
            connection_id=conn_id,
            user=fake_user,
            session=fake_session,
        )

    assert len(captured_jobs) == 1, (
        f"ai_analyze должен создать ровно одну Job row, получили "
        f"{len(captured_jobs)}"
    )
    job = captured_jobs[0]
    # Колонка — source of truth.
    assert job.workspace_id == workspace_id
    # JSONB payload — без workspace_id (иначе дублирование).
    assert "workspace_id" not in job.payload, (
        f"public.jobs.payload не должен содержать workspace_id — он уже "
        f"в FK-колонке public.jobs.workspace_id. Got payload={job.payload!r}"
    )
    # connection_id в stored payload остаётся (для UI / audit трейла).
    assert job.payload.get("connection_id") == str(conn_id)
