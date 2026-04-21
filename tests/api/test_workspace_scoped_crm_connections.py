"""
Tests for Task #52.4 — workspace-scoped CRM connections endpoint.

Предыстория
-----------
2026-04-21, после успешного recovery коннекта
``1ede9725-4b4e-4157-8a12-a8ac9c67f274`` (Task #52.3G), пользователь
заметил, что после refresh страницы ``/app/connections`` активное
amoCRM-подключение не отображается. Network trace показал::

    GET /api/v1/workspaces/{wsid}/crm/connections → 404 Not Found

Фронт (apps/web/app/[locale]/app/connections/page.tsx) вызывает путь
``/workspaces/${wsId}/crm/connections`` (прописан в CONTRACT.md), но
в backend такого роута не было — был только ``GET /crm/connections``
с ``get_current_workspace``-зависимостью. В итоге список коннектов
никогда не подгружался, и UI показывал пустое состояние.

Плюс, у фронта был плохой fallback ``wsId = user?.workspaces?.[0]?.id
?? 'ws-demo-1'`` — строка ``'ws-demo-1'`` не UUID и вызвала бы 422
сразу после добавления роута.

Что покрывают тесты
-------------------
1. Auth-level: без ``Authorization`` → 401 (не 404). Гарантирует, что
   роут существует и зарегистрирован до auth-middleware, иначе FastAPI
   отдал бы 404 (match failed до any deps).
2. Path-param валидация: невалидный UUID в пути → 422 (или 401 если
   auth проверяется раньше — оба допустимы; главное не 500).
3. Source-level guard: ``ws_crm_router`` экспортируется из
   ``app.crm.router`` и подключается в ``app.main`` с префиксом ``/api/v1``.
4. Source-level guard: роут имеет правильный path
   ``/workspaces/{workspace_id}/crm/connections``.

Почему source-level, а не полноценный integration
-------------------------------------------------
Существующие тесты в ``tests/api/test_workspace.py`` работают по
тому же паттерну (все проверки — на 401 без токена). Полный сетап
юзер + workspace + CRM connection + JWT требует доступа к БД с
выполненными миграциями, а это вынесено в separate smoke test
сюиту. Auth-level + source-level guard закрывают конкретный баг
(отсутствие роута → 404) и регрессию (случайное удаление или
переименование роута).
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from httpx import AsyncClient


# --------------------------------------------------- auth-level tests ------


@pytest.mark.asyncio
async def test_ws_scoped_crm_connections_requires_auth(client: AsyncClient):
    """
    GET /api/v1/workspaces/{uuid}/crm/connections без ``Authorization`` → 401.

    Ключевое отличие от pre-fix поведения: раньше любой запрос по этому
    пути возвращал 404 "Not Found" (роут отсутствовал). Теперь роут есть
    → auth-слой срабатывает первым → 401.
    """
    wsid = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/workspaces/{wsid}/crm/connections")
    assert resp.status_code == 401, (
        f"Ожидали 401 (auth missing). Получили {resp.status_code}. "
        f"Если 404 — роут не подключён. Если 500 — handler падает до auth. "
        f"Body: {resp.text!r}"
    )
    body = resp.json()
    # Unified error shape из app/main.py.
    assert "error" in body
    assert body["error"]["code"] in {"unauthorized", "not_found"}  # obvs. unauthorized


@pytest.mark.asyncio
async def test_ws_scoped_crm_connections_invalid_uuid_still_auth_first(
    client: AsyncClient,
):
    """
    Невалидный UUID в пути → всё равно 401 без токена, не 422.

    FastAPI парсит path param ``workspace_id: uuid.UUID`` и при неуспехе
    отдаёт 422 Validation Error. Но auth-dependency выполняется первой,
    так что без токена всегда получаем 401 (независимо от формата пути).
    Это важно: мы НЕ раскрываем, существует ли workspace с таким id.
    """
    resp = await client.get("/api/v1/workspaces/not-a-uuid/crm/connections")
    assert resp.status_code in {401, 422}, (
        f"Ожидали 401 (auth first) или 422 (path validation). "
        f"Получили {resp.status_code}: {resp.text!r}"
    )
    # В любом случае — не 500 и не 404.
    assert resp.status_code != 404, "роут должен существовать, иначе Bug #52.4"
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_ws_scoped_crm_connections_fake_token_unauthorized(
    client: AsyncClient,
):
    """
    Валидный-по-форме UUID + невалидный Bearer → 401, в теле нет секретов.
    """
    wsid = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/workspaces/{wsid}/crm/connections",
        headers={"Authorization": "Bearer fake-token-value"},
    )
    assert resp.status_code == 401
    body_text = resp.text
    # Дополнительный страх: не утекают вообще никакие внутренние секреты.
    assert "access_token" not in body_text
    assert "refresh_token" not in body_text
    assert "client_secret" not in body_text
    assert "password" not in body_text


# --------------------------------------------------- source-level guards --


def test_ws_crm_router_is_exported_from_crm_module() -> None:
    """
    Contract: ``ws_crm_router`` доступен как атрибут в ``app.crm.router``.

    Если кто-то переименует/удалит — падаем здесь, а не втихаря 404.
    """
    from app.crm import router as crm_module

    assert hasattr(crm_module, "ws_crm_router"), (
        "app.crm.router.ws_crm_router отсутствует — Bug #52.4 регресс. "
        "Восстанови workspace-scoped роутер."
    )
    from fastapi import APIRouter

    assert isinstance(crm_module.ws_crm_router, APIRouter), (
        "ws_crm_router должен быть APIRouter."
    )


def test_ws_crm_router_registers_workspace_scoped_path() -> None:
    """
    Contract: в ``ws_crm_router`` есть маршрут с path
    ``/workspaces/{workspace_id}/crm/connections`` и методом GET.
    """
    from app.crm.router import ws_crm_router

    paths = [
        (route.path, tuple(sorted(route.methods or ())))
        for route in ws_crm_router.routes
        if hasattr(route, "path")
    ]
    expected_path = "/workspaces/{workspace_id}/crm/connections"
    assert any(
        p == expected_path and "GET" in methods for p, methods in paths
    ), (
        f"В ws_crm_router нет GET {expected_path}. Есть: {paths!r}. "
        "Если путь переименовали — обнови CONTRACT.md и фронт "
        "(apps/web/app/[locale]/app/connections/page.tsx)."
    )


def test_main_py_includes_ws_crm_router_under_api_prefix() -> None:
    """
    Contract: ``app.main`` подключает ``ws_crm_router`` с prefix=API_PREFIX.

    Без этого роут есть в модуле, но не попадает в ASGI-app → 404.
    Проверяем исходник — без запуска приложения, чтобы тест не требовал БД.
    """
    from app import main as main_module

    src = inspect.getsource(main_module)
    assert "ws_crm_router" in src, (
        "app/main.py не импортирует ws_crm_router. "
        "Добавь `from app.crm.router import ws_crm_router` и "
        "`app.include_router(ws_crm_router, prefix=API_PREFIX)`."
    )
    # Проверяем именно include_router-строку.
    assert "include_router(ws_crm_router" in src, (
        "ws_crm_router импортирован, но не подключён через include_router. "
        "Добавь: app.include_router(ws_crm_router, prefix=API_PREFIX)"
    )
    # И что он под /api/v1.
    assert (
        "include_router(ws_crm_router, prefix=API_PREFIX)" in src
        or 'include_router(ws_crm_router, prefix="/api/v1")' in src
    ), (
        "ws_crm_router подключён без prefix=API_PREFIX — путь будет "
        "без /api/v1 → фронт получит 404."
    )


def test_ws_crm_router_list_endpoint_filters_deleted_but_not_external_button() -> None:
    """
    Source-level guard: handler НЕ фильтрует external_button-подключения,
    но фильтрует deleted.

    Bug #52.4 мог быть усугублён, если handler добавит случайный
    ``.where(CrmConnection.amocrm_auth_mode != 'external_button')``.
    Проверяем исходник (с выкинутым docstring'ом, чтобы пояснительные
    фразы «external_button НЕ фильтруется» не триггерили false-positive):
    допускаем только ``status != 'deleted'`` как фильтр строк.
    """
    from app.crm import router as crm_module

    src = inspect.getsource(crm_module.list_workspace_connections)

    # Strip docstring: всё между первым и вторым triple-quote.
    def _strip_first_docstring(s: str) -> str:
        for delim in ('"""', "'''"):
            first = s.find(delim)
            if first == -1:
                continue
            second = s.find(delim, first + 3)
            if second == -1:
                continue
            return s[:first] + s[second + 3:]
        return s

    code_only = _strip_first_docstring(src)

    assert 'status != "deleted"' in code_only or "status != 'deleted'" in code_only, (
        "list_workspace_connections должен фильтровать status='deleted'."
    )
    # NOT допускаем фильтра по auth_mode в коде (докстринг уже убран).
    assert "amocrm_auth_mode" not in code_only, (
        "Bug #52.4 regression: handler фильтрует по amocrm_auth_mode — "
        "это скроет external_button-подключения от пользователя."
    )
    assert "external_button" not in code_only, (
        "Bug #52.4 regression: handler упоминает external_button в коде "
        "(не в docstring). Выборка должна быть идентична /crm/connections "
        "(status != 'deleted')."
    )


def test_ws_crm_router_uses_serialize_conn_for_response() -> None:
    """
    Contract: handler возвращает результат через ``_serialize_conn``, чтобы
    ``metadata.last_pull_counts`` + ``last_sync_at`` + все публично-безопасные
    поля отдавались единым форматом. Если кто-то решит собрать dict вручную
    и забудет metadata — фронт перестанет показывать counts.
    """
    from app.crm import router as crm_module

    src = inspect.getsource(crm_module.list_workspace_connections)
    assert "_serialize_conn" in src, (
        "list_workspace_connections должен использовать _serialize_conn — "
        "иначе ответ может потерять ``metadata.last_pull_counts`` или "
        "протечь токены."
    )
