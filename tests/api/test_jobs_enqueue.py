"""
Контрактные тесты ``app.core.jobs.enqueue`` — фиксируют, что payload
разворачивается в **kwargs worker-функции, а не передаётся позиционно.

Bug D (Task #52.3D, обнаружен в live-прогоне #52.3 после фикса Bug C)
---------------------------------------------------------------------
До фикса ``enqueue()`` вызывал ``queue.enqueue(func_path, payload, **kw)``,
и RQ клал payload dict как первый ПОЗИЦИОННЫЙ аргумент — это попадало
на место ``connection_id``/``workspace_id``/``billing_account_id``/``text_in``
и ломалось либо на ``psycopg2.ProgrammingError: can't adapt type 'dict'``,
либо ниже по стеку.

Фикс: использовать ``queue.enqueue_call(func=..., kwargs=payload, ...)``,
чтобы payload распаковывался в kwargs. Все worker-jobs имеют сигнатуру
``def job(<entity>_id: str, *, ...)``; имена ключей в payload совпадают
с именами параметров (подтверждено signature inventory для 16 kinds).

Тесты:
  1. enqueue_call вызывается, а не enqueue (проверка API-контракта).
  2. Позиционные args пустые; payload передан как kwargs.
  3. depends_on и job_id правильно пробрасываются в RQ.
  4. Unknown kind даёт ValueError (regression — уже было, но закрепляем).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.jobs import enqueue


class _FakeJob:
    def __init__(self, job_id: str):
        self.id = job_id


@pytest.fixture
def fake_queue():
    """Подменяем queue объект и наблюдаем за вызовами."""
    q = MagicMock()
    q.enqueue_call = MagicMock(return_value=_FakeJob("fake-rq-id-12345"))
    q.enqueue = MagicMock(
        side_effect=AssertionError(
            "Bug D regression: enqueue() must not call queue.enqueue — "
            "use queue.enqueue_call with kwargs=payload instead"
        )
    )
    with patch("app.core.jobs._get_queue", return_value=q):
        yield q


def test_enqueue_uses_enqueue_call_with_kwargs_payload(fake_queue):
    """Главный контракт Bug D fix: payload → kwargs, не args."""
    payload = {"connection_id": "1ede9725-4b4e-4157-8a12-a8ac9c67f274"}
    rq_id = enqueue("bootstrap_tenant_schema", payload)

    assert rq_id == "fake-rq-id-12345"
    fake_queue.enqueue.assert_not_called()
    fake_queue.enqueue_call.assert_called_once()

    call = fake_queue.enqueue_call.call_args
    # Позиционные args должны быть пустые — func передан как kwarg.
    assert call.args == (), (
        f"Bug D regression: positional args must be empty, got {call.args!r}"
    )
    assert call.kwargs["func"] == "worker.jobs.crm.bootstrap_tenant_schema"
    assert call.kwargs["kwargs"] == payload, (
        f"Bug D regression: payload must be forwarded as kwargs, "
        f"got kwargs={call.kwargs.get('kwargs')!r}"
    )
    # job_id всегда генерируется.
    assert "job_id" in call.kwargs
    assert len(call.kwargs["job_id"]) > 0
    # depends_on не передавали — не должно быть в вызове.
    assert "depends_on" not in call.kwargs


def test_enqueue_forwards_depends_on(fake_queue):
    payload = {
        "connection_id": "1ede9725-4b4e-4157-8a12-a8ac9c67f274",
        "first_pull": True,
        "deals_limit": 100,
    }
    parent_rq_id = "parent-job-id-abc"
    enqueue("pull_amocrm_core", payload, depends_on=parent_rq_id)

    call = fake_queue.enqueue_call.call_args
    assert call.kwargs["func"] == "worker.jobs.crm_pull.pull_amocrm_core"
    assert call.kwargs["kwargs"] == payload
    assert call.kwargs["depends_on"] == parent_rq_id


def test_enqueue_resolves_module_override_for_pull_amocrm_core(fake_queue):
    """pull_amocrm_core живёт в crm_pull модуле, не в crm."""
    enqueue("pull_amocrm_core", {"connection_id": "x"})
    call = fake_queue.enqueue_call.call_args
    assert call.kwargs["func"] == "worker.jobs.crm_pull.pull_amocrm_core"


def test_enqueue_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Unknown job kind"):
        enqueue("definitely_not_a_real_kind", {"connection_id": "x"})


def test_enqueue_fallback_returns_uuid_on_queue_failure():
    """Если worker не поднят (Redis/очередь падает) — enqueue возвращает
    фиктивный UUID, чтобы API не падал. Контракт из docstring."""
    q = MagicMock()
    q.enqueue_call = MagicMock(side_effect=ConnectionError("redis down"))
    with patch("app.core.jobs._get_queue", return_value=q):
        rq_id = enqueue("bootstrap_tenant_schema", {"connection_id": "x"})
    assert isinstance(rq_id, str)
    # Фиктивный id — стандартный UUID v4 (36 символов).
    assert len(rq_id) == 36


# --------------------------------------------------- Task #52.6 --------
#
# Контракт: ``job_row_id`` попадает в worker-kwargs, но НЕ мутирует
# исходный payload, который API хранит в ``public.jobs.payload``.
#
# До Task #52.6 enqueue() не принимал job_row_id — воркер получал None
# через default, ``mark_job_running/succeeded/failed`` тихо no-op'или
# (``if not job_row_id: return``), и ``public.jobs.status`` навсегда
# оставался ``queued``, хотя RQ job фактически отработал.
# -----------------------------------------------------------------------


def test_enqueue_injects_job_row_id_into_worker_kwargs(fake_queue):
    """
    job_row_id должен попасть в kwargs, которые RQ передаст worker-функции.
    Без этого воркер получит ``job_row_id=None`` и не сможет обновить
    статус public.jobs (см. apps/worker/worker/jobs/_common.py:mark_job_*).
    """
    job_row_id = "11111111-2222-3333-4444-555555555555"
    payload = {"connection_id": "1ede9725-4b4e-4157-8a12-a8ac9c67f274"}
    enqueue("build_export_zip", payload, job_row_id=job_row_id)

    call = fake_queue.enqueue_call.call_args
    kwargs_sent_to_worker = call.kwargs["kwargs"]
    assert kwargs_sent_to_worker.get("job_row_id") == job_row_id, (
        "Task #52.6 regression: enqueue должен добавлять job_row_id в worker kwargs, "
        f"получили kwargs={kwargs_sent_to_worker!r}"
    )
    # connection_id тоже должен остаться (контракт Bug D).
    assert (
        kwargs_sent_to_worker.get("connection_id")
        == "1ede9725-4b4e-4157-8a12-a8ac9c67f274"
    )


def test_enqueue_does_not_mutate_input_payload(fake_queue):
    """
    Ключевой инвариант: исходный payload dict (который вызывающий код хранит
    в public.jobs.payload) НЕ должен содержать job_row_id. Иначе id дублируется
    в двух колонках (public.jobs.id и public.jobs.payload.job_row_id)
    и рассинхрон неизбежен.
    """
    payload = {"connection_id": "1ede9725-4b4e-4157-8a12-a8ac9c67f274"}
    original = dict(payload)  # снимок до вызова
    enqueue(
        "build_export_zip",
        payload,
        job_row_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )

    assert payload == original, (
        "Task #52.6 regression: enqueue() не должен мутировать входной payload. "
        f"Ожидали {original!r}, получили {payload!r}. "
        "API хранит этот dict в public.jobs.payload — мутация перетрёт stored state."
    )
    assert "job_row_id" not in payload, (
        "Task #52.6 regression: job_row_id просочился в stored payload — "
        "используй shallow copy в enqueue()."
    )


def test_enqueue_without_job_row_id_omits_key_from_kwargs(fake_queue):
    """
    Если вызывающий код не передал job_row_id (legacy-путь) — ключ НЕ должен
    появляться в worker-kwargs. Иначе worker получит ``job_row_id="None"``
    или подобное, и mark_job_* попытается UPDATE non-existent row.
    """
    payload = {"connection_id": "1ede9725-4b4e-4157-8a12-a8ac9c67f274"}
    enqueue("build_export_zip", payload)  # job_row_id omitted

    call = fake_queue.enqueue_call.call_args
    worker_kwargs = call.kwargs["kwargs"]
    assert "job_row_id" not in worker_kwargs, (
        f"enqueue() без job_row_id должен не класть ключ в kwargs; "
        f"получили worker_kwargs={worker_kwargs!r}"
    )


def test_enqueue_job_row_id_none_explicit_omits_key(fake_queue):
    """
    Явный ``job_row_id=None`` эквивалентен его отсутствию — ключ не в kwargs.
    (Защита от случая, когда вызывающий код передаёт None как sentinel.)
    """
    payload = {"connection_id": "x"}
    enqueue("build_export_zip", payload, job_row_id=None)
    call = fake_queue.enqueue_call.call_args
    assert "job_row_id" not in call.kwargs["kwargs"]
