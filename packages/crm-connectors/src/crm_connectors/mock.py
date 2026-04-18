"""
MockCRMConnector — основной коннектор для MVP (`MOCK_CRM_MODE=true`).

Возвращает данные из JSON-фикстур в `crm_connectors/fixtures/`.
Поддерживает «раздувание» выборок до запрошенного `limit` (например, 10 deals
в фикстуре можно расширить до 100, чтобы протестировать пагинацию).

Никаких сетевых вызовов. Никаких реальных токенов — только синтетика.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import Any, Iterable, Iterator, Optional

from .base import (
    CRMConnector,
    RawCall,
    RawCompany,
    RawContact,
    RawDeal,
    RawMessage,
    RawNote,
    RawPipeline,
    RawStage,
    RawTask,
    RawUser,
    TokenPair,
)
from .enums import Provider

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

# По спецификации: mock-токены живут 30 дней.
_MOCK_TOKEN_TTL = timedelta(days=30)

# Маппинг amoCRM `status_id` → human status. Совпадает со значениями в
# `amo_pipelines.json` (системные стадии 142 / 143).
_AMO_SYSTEM_STAGES: dict[int, str] = {
    142: "won",
    143: "lost",
}

# Маппинг amoCRM stage type → kind (open/won/lost).
_AMO_STAGE_TYPE_TO_KIND: dict[int, str] = {
    0: "open",
    1: "won",
    2: "lost",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> Any:
    """Читает JSON-фикстуру из `crm_connectors/fixtures/<name>`."""
    pkg = resources.files("crm_connectors").joinpath("fixtures").joinpath(name)
    with pkg.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ts(value: Any) -> Optional[datetime]:
    """unix-timestamp (int) или ISO-8601 (str) → tz-aware datetime в UTC."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    if isinstance(value, str):
        # Простейший парсер ISO. Для prod — `dateutil.parser.isoparse`.
        try:
            from dateutil.parser import isoparse  # type: ignore

            dt = isoparse(value)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def _short_token(prefix: str) -> str:
    """`mock_access_a1b2c3d4` — 8 случайных hex-символов."""
    return f"{prefix}_{secrets.token_hex(4)}"


def _amo_status_from_stage(status_id: int, stage_kind_map: dict[int, int]) -> str:
    """Восстанавливает human status (`open|won|lost`) из amo `status_id`."""
    if status_id in _AMO_SYSTEM_STAGES:
        return _AMO_SYSTEM_STAGES[status_id]
    stage_type = stage_kind_map.get(status_id, 0)
    return _AMO_STAGE_TYPE_TO_KIND.get(stage_type, "open")


# ---------------------------------------------------------------------------
# MockCRMConnector
# ---------------------------------------------------------------------------


class MockCRMConnector(CRMConnector):
    """
    Mock-реализация `CRMConnector` для MVP.

    Параметры:
        provider: какой реальный провайдер «эмулируется». В БД будет записан
            он же (например, `amocrm`). Флаг is_mock — в `metadata`.
        web_callback_base: базовый URL веба, на который мок будет «редиректить»
            после imitation OAuth. По умолчанию — `http://localhost:3000`.

    Источник данных — JSON-фикстуры. Все методы — синхронные и детерминированные
    (за исключением случайных токенов в OAuth).
    """

    def __init__(
        self,
        provider: Provider = Provider.MOCK,
        *,
        web_callback_base: str = "http://localhost:3000",
    ) -> None:
        self.provider = provider
        self._web_callback_base = web_callback_base.rstrip("/")
        # Lazy-кэш для фикстур, чтобы не парсить JSON каждый вызов.
        self._cache: dict[str, Any] = {}

    # ----- внутренние утилиты -------------------------------------------------

    def _get(self, name: str) -> Any:
        if name not in self._cache:
            self._cache[name] = _load_fixture(name)
        return self._cache[name]

    def _stage_kind_index(self) -> dict[int, int]:
        """Индекс `status_id → stage.type` по всем воронкам."""
        idx: dict[int, int] = {}
        for pipeline in self._get("amo_pipelines.json"):
            for stage in pipeline["stages"]:
                idx[stage["id"]] = stage.get("type", 0)
        return idx

    # ----- OAuth --------------------------------------------------------------

    def oauth_authorize_url(self, state: str, redirect_uri: str) -> str:
        """
        В моке возвращаем локальный URL веба, чтобы UI смог
        сделать redirect → callback → exchange_code.
        """
        from urllib.parse import urlencode

        params = urlencode({"state": state, "redirect_uri": redirect_uri})
        return f"{self._web_callback_base}/app/connections/mock-callback?{params}"

    def exchange_code(self, code: str, redirect_uri: str) -> TokenPair:
        """Возвращает фейковый TokenPair, expires_at = now + 30 дней."""
        now = datetime.now(tz=timezone.utc)
        return TokenPair(
            access_token=_short_token("mock_access"),
            refresh_token=_short_token("mock_refresh"),
            expires_at=now + _MOCK_TOKEN_TTL,
            raw={"mock": True, "code": code, "redirect_uri": redirect_uri},
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        """Mock refresh всегда успешен (см. `docs/security/OAUTH_TOKENS.md`, §Тест-режим)."""
        now = datetime.now(tz=timezone.utc)
        return TokenPair(
            access_token=_short_token("mock_access"),
            refresh_token=_short_token("mock_refresh"),
            expires_at=now + _MOCK_TOKEN_TTL,
            raw={"mock": True, "refreshed_from": refresh_token[:6] + "***"},
        )

    # ----- Account / Audit ----------------------------------------------------

    def fetch_account(self, access_token: str) -> dict[str, Any]:
        return {
            "id": f"mock-{uuid.uuid4().hex[:8]}",
            "name": "Mock amoCRM",
            "subdomain": "mock-amo",
            "country": "RU",
            "currency": "RUB",
            "is_mock": True,
        }

    def audit(self, access_token: str) -> dict[str, Any]:
        """Возвращает фикстурный summary с реалистичными счётчиками."""
        return self._get("amo_audit_summary.json")

    # ----- Fetchers -----------------------------------------------------------

    def _paginate(
        self,
        items: list[Any],
        limit: Optional[int],
    ) -> Iterator[Any]:
        """
        Если `limit` > len(items), «раздуваем» список повторами с модификацией
        crm_id (чтобы оставались уникальные external_id). Это нужно, чтобы
        протестировать пагинацию/нагрузку без необходимости вручную писать 100
        deals в фикстуру.
        """
        if not items:
            return iter(())
        if limit is None or limit <= len(items):
            yield from items[: limit if limit is not None else len(items)]
            return

        produced = 0
        cycle_idx = 0
        while produced < limit:
            base = items[produced % len(items)]
            if cycle_idx == 0:
                yield base
            else:
                # Дублируем, но меняем id, чтобы не нарушать UNIQUE(external_id).
                clone = dict(base) if isinstance(base, dict) else base
                if isinstance(clone, dict) and "id" in clone:
                    clone = {**clone, "id": f"{clone['id']}-r{cycle_idx}"}
                yield clone
            produced += 1
            if produced % len(items) == 0:
                cycle_idx += 1

    @staticmethod
    def _filter_since(items: list[dict[str, Any]], since: Optional[datetime], key: str) -> list[dict[str, Any]]:
        if since is None:
            return items
        threshold = since.timestamp()
        return [it for it in items if (it.get(key) or 0) >= threshold]

    def fetch_deals(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawDeal]:
        raw = self._get("amo_deals.json")
        raw = self._filter_since(raw, since, "created_at")
        stage_idx = self._stage_kind_index()
        for d in self._paginate(raw, limit):
            yield RawDeal(
                crm_id=str(d["id"]),
                name=d.get("name"),
                price=float(d["price"]) if d.get("price") is not None else None,
                currency=d.get("currency"),
                status=_amo_status_from_stage(d.get("status_id", 0), stage_idx),
                pipeline_id=str(d["pipeline_id"]) if d.get("pipeline_id") else None,
                stage_id=str(d["status_id"]) if d.get("status_id") else None,
                responsible_user_id=str(d["responsible_user_id"]) if d.get("responsible_user_id") else None,
                contact_id=str(d["contact_id"]) if d.get("contact_id") else None,
                company_id=str(d["company_id"]) if d.get("company_id") else None,
                source=d.get("source"),
                created_at=_ts(d.get("created_at")),
                updated_at=_ts(d.get("updated_at")),
                closed_at=_ts(d.get("closed_at")),
                raw_payload=d,
            )

    def fetch_contacts(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawContact]:
        raw = self._get("amo_contacts.json")
        raw = self._filter_since(raw, since, "created_at")
        for c in self._paginate(raw, limit):
            yield RawContact(
                crm_id=str(c["id"]),
                name=c.get("name"),
                phone=c.get("phone"),
                email=c.get("email"),
                responsible_user_id=str(c["responsible_user_id"]) if c.get("responsible_user_id") else None,
                company_id=str(c["company_id"]) if c.get("company_id") else None,
                created_at=_ts(c.get("created_at")),
                updated_at=_ts(c.get("updated_at")),
                raw_payload=c,
            )

    def fetch_companies(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCompany]:
        raw = self._get("amo_companies.json")
        raw = self._filter_since(raw, since, "created_at")
        for c in self._paginate(raw, limit):
            yield RawCompany(
                crm_id=str(c["id"]),
                name=c.get("name"),
                inn=c.get("inn"),
                phone=c.get("phone"),
                website=c.get("website"),
                responsible_user_id=str(c["responsible_user_id"]) if c.get("responsible_user_id") else None,
                created_at=_ts(c.get("created_at")),
                updated_at=_ts(c.get("updated_at")),
                raw_payload=c,
            )

    def fetch_pipelines(self, access_token: str) -> Iterable[RawPipeline]:
        for p in self._get("amo_pipelines.json"):
            yield RawPipeline(
                crm_id=str(p["id"]),
                name=p["name"],
                is_default=bool(p.get("is_main", False)),
                sort_order=p.get("sort"),
                raw_payload=p,
            )

    def fetch_stages(self, access_token: str) -> Iterable[RawStage]:
        for p in self._get("amo_pipelines.json"):
            for s in p["stages"]:
                kind = _AMO_STAGE_TYPE_TO_KIND.get(s.get("type", 0), "open")
                yield RawStage(
                    crm_id=str(s["id"]),
                    pipeline_id=str(p["id"]),
                    name=s["name"],
                    sort_order=s.get("sort"),
                    kind=kind,  # type: ignore[arg-type]
                    color=s.get("color"),
                    raw_payload=s,
                )

    def fetch_users(self, access_token: str) -> Iterable[RawUser]:
        for u in self._get("amo_users.json"):
            yield RawUser(
                crm_id=str(u["id"]),
                name=u.get("name"),
                email=u.get("email"),
                role=u.get("role"),
                is_active=bool(u.get("is_active", True)),
                created_at=_ts(u.get("created_at")),
                raw_payload=u,
            )

    def fetch_calls(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCall]:
        raw = self._get("amo_calls.json")
        raw = self._filter_since(raw, since, "created_at")
        for c in self._paginate(raw, limit):
            yield RawCall(
                crm_id=str(c["id"]),
                deal_id=str(c["deal_id"]) if c.get("deal_id") else None,
                contact_id=str(c["contact_id"]) if c.get("contact_id") else None,
                user_id=str(c["user_id"]) if c.get("user_id") else None,
                direction=c.get("direction", "out"),
                phone=c.get("phone"),
                duration_seconds=c.get("duration"),
                result=c.get("result"),
                recording_url=c.get("recording_url"),
                created_at=_ts(c.get("created_at")),
                raw_payload=c,
            )

    def fetch_messages(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawMessage]:
        raw = self._get("amo_messages.json")
        raw = self._filter_since(raw, since, "sent_at")
        for m in self._paginate(raw, limit):
            yield RawMessage(
                crm_id=str(m["id"]),
                chat_id=m.get("chat_id"),
                deal_id=str(m["deal_id"]) if m.get("deal_id") else None,
                contact_id=str(m["contact_id"]) if m.get("contact_id") else None,
                author_kind=m.get("author_kind", "client"),
                author_user_id=str(m["author_user_id"]) if m.get("author_user_id") else None,
                channel=m.get("channel"),
                text=m.get("text"),
                sent_at=_ts(m.get("sent_at")),
                raw_payload=m,
            )

    def fetch_tasks(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawTask]:
        raw = self._get("amo_tasks.json")
        raw = self._filter_since(raw, since, "created_at")
        for t in self._paginate(raw, limit):
            yield RawTask(
                crm_id=str(t["id"]),
                deal_id=str(t["deal_id"]) if t.get("deal_id") else None,
                contact_id=str(t["contact_id"]) if t.get("contact_id") else None,
                responsible_user_id=str(t["responsible_user_id"]) if t.get("responsible_user_id") else None,
                kind=t.get("task_type"),
                text=t.get("text"),
                is_completed=bool(t.get("is_completed", False)),
                due_at=_ts(t.get("complete_till")),
                completed_at=_ts(t.get("completed_at")),
                created_at=_ts(t.get("created_at")),
                raw_payload=t,
            )

    def fetch_notes(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawNote]:
        raw = self._get("amo_notes.json")
        raw = self._filter_since(raw, since, "created_at")
        for n in self._paginate(raw, limit):
            yield RawNote(
                crm_id=str(n["id"]),
                deal_id=str(n["deal_id"]) if n.get("deal_id") else None,
                contact_id=str(n["contact_id"]) if n.get("contact_id") else None,
                author_user_id=str(n["author_user_id"]) if n.get("author_user_id") else None,
                body=n.get("text"),
                created_at=_ts(n.get("created_at")),
                raw_payload=n,
            )


__all__ = ["MockCRMConnector"]
