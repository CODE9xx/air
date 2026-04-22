"""
Tests for Task #52.5 — trial export endpoint.

Что фиксируется
---------------
1. Роут ``POST /api/v1/crm/connections/{connection_id}/trial-export``
   существует: без Authorization → 401 (не 404 и не 500).
2. Handler ``trial_export`` ставит RQ job с ``kind="build_export_zip"`` и
   payload ``{"connection_id": <uuid>, "trial": True}``.
3. Такой payload совместим с worker-сигнатурой
   ``build_export_zip(connection_id, *, job_row_id=None, trial=False)``
   (fix из той же задачи, см. apps/worker/worker/jobs/export.py).
4. Status code handler'а — 202 Accepted.

Предыстория (Task #52.5 root cause)
-----------------------------------
Frontend вызывал несуществующий ``POST /workspaces/{ws}/export/jobs`` → 404,
UI показывал toast «Ошибка». Даже если исправить путь на корректный
``/crm/connections/{id}/trial-export`` — worker падал с TypeError, потому
что ``build_export_zip`` не принимал ``trial`` kwarg (latent regression
из Task #52.3D, Bug D). Плюс third bug: backend enqueue'ил
build_export_zip, алиас full_export (stub), вместо реального trial_export.

Эти тесты гарантируют, что все три слоя снова не разойдутся: контракт
endpoint↔payload↔worker signature закреплён здесь и в
``tests/worker/test_export_trial_branch.py``.
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from httpx import AsyncClient


# --------------------------------------------------- auth-level tests ------


@pytest.mark.asyncio
async def test_trial_export_requires_auth(client: AsyncClient):
    """
    POST /api/v1/crm/connections/{uuid}/trial-export без Authorization → 401.

    Ключевое: не 404. Если 404 — роут не зарегистрирован, и фронт снова
    упадёт в тот же класс бага, что и до Task #52.5.
    """
    connid = str(uuid.uuid4())
    resp = await client.post(f"/api/v1/crm/connections/{connid}/trial-export")
    assert resp.status_code == 401, (
        f"Ожидали 401 (auth missing). Получили {resp.status_code}. "
        f"Если 404 — роут пропал. Body: {resp.text!r}"
    )


@pytest.mark.asyncio
async def test_trial_export_invalid_uuid_still_auth_first(client: AsyncClient):
    """Невалидный UUID → 401 (или 422 на FastAPI-валидации), не 404/500."""
    resp = await client.post("/api/v1/crm/connections/not-a-uuid/trial-export")
    assert resp.status_code in {401, 422}, (
        f"Ожидали 401/422. Получили {resp.status_code}: {resp.text!r}"
    )
    assert resp.status_code != 404, "роут должен существовать"
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_trial_export_fake_token_unauthorized_no_secret_leak(
    client: AsyncClient,
):
    """
    Невалидный Bearer → 401. В теле ответа не должны всплывать секреты
    (token/password/client_secret).
    """
    connid = str(uuid.uuid4())
    resp = await client.post(
        f"/api/v1/crm/connections/{connid}/trial-export",
        headers={"Authorization": "Bearer fake-token-value"},
    )
    assert resp.status_code == 401
    body = resp.text
    for sensitive in ("access_token", "refresh_token", "client_secret", "password"):
        assert sensitive not in body, f"leaked '{sensitive}' in 401 body: {body!r}"


# --------------------------------------------------- source-level guards --


def test_trial_export_handler_enqueues_build_export_zip_with_trial_true() -> None:
    """
    Source-level guard (главный инвариант Task #52.5):
    handler ``trial_export`` ставит RQ-job с kind=build_export_zip и
    payload, содержащим ``trial=True``. Без этого bus line worker→router
    снова расходится.
    """
    from app.crm import router as crm_router

    src = inspect.getsource(crm_router.trial_export)

    assert '"build_export_zip"' in src or "'build_export_zip'" in src, (
        "Handler trial_export должен enqueue'ить kind=build_export_zip. "
        "Если переехали на отдельный JobKind.TRIAL_EXPORT — обнови "
        "этот тест + миграцию ck_job_kind + JobKind enum."
    )

    assert '"trial": True' in src or "'trial': True" in src, (
        "Handler trial_export должен передавать trial=True в payload. "
        "Иначе worker.build_export_zip уйдёт в full_export-ветку (stub) "
        "и не создаст тестовые deals."
    )
    assert "connection_id" in src


def test_trial_export_endpoint_path_matches_frontend_contract() -> None:
    """
    Contract: POST /connections/{connection_id}/trial-export в crm-router.

    Фронт (apps/web/app/[locale]/app/connections/[id]/page.tsx,
    функция startTrialExport) делает POST на этот путь без тела.
    Если кто-то переименует — фронт получит 404 (тот самый баг #52.5).
    """
    from app.crm.router import router as crm_router

    paths = [
        (route.path, tuple(sorted(route.methods or ())))
        for route in crm_router.routes
        if hasattr(route, "path")
    ]
    expected = "/connections/{connection_id}/trial-export"
    assert any(
        p == expected and "POST" in methods for p, methods in paths
    ), (
        f"В crm_router нет POST {expected}. Есть: {paths!r}. "
        "Переименовали путь? Обнови фронт startTrialExport."
    )


def test_trial_export_returns_202_accepted() -> None:
    """Contract: handler декорирован status_code=HTTP_202_ACCEPTED."""
    from app.crm.router import router as crm_router

    for route in crm_router.routes:
        if (
            getattr(route, "path", "") == "/connections/{connection_id}/trial-export"
            and "POST" in (route.methods or set())
        ):
            assert route.status_code == 202, (
                f"trial-export должен возвращать 202 Accepted, получил "
                f"{route.status_code}."
            )
            return
    pytest.fail("POST /connections/{connection_id}/trial-export route not found")


def test_trial_export_payload_keys_match_worker_signature() -> None:
    """
    Cross-package contract: ключи payload из router (``connection_id``,
    ``trial``) ДОЛЖНЫ существовать в сигнатуре worker-функции
    build_export_zip, иначе RQ enqueue_call(kwargs=payload) даст TypeError
    (regression Bug D из Task #52.3D).

    Важно: проверяем по исходнику handler'а и импорту worker-модуля —
    если worker пакет недоступен, тест помечается как skipped, не падает
    (в api-контейнере PYTHONPATH на apps/worker не гарантирован).
    """
    from app.crm import router as crm_router

    src = inspect.getsource(crm_router.trial_export)
    # Грубо вычленим payload-ключи.
    expected_keys = {"connection_id", "trial"}
    for k in expected_keys:
        assert k in src, f"payload-key {k!r} не найден в handler trial_export"

    # Опциональная проверка worker signature — если пакет доступен.
    try:
        from worker.jobs.export import build_export_zip  # type: ignore[import-not-found]
    except Exception:
        pytest.skip("worker package not importable in this runtime — "
                    "signature-level guard покрыт tests/worker/test_export_trial_branch.py")

    sig = inspect.signature(build_export_zip)
    missing = expected_keys - set(sig.parameters)
    assert not missing, (
        f"build_export_zip signature не принимает {missing}. "
        "Task #52.5 fix не применён — обнови apps/worker/worker/jobs/export.py."
    )
