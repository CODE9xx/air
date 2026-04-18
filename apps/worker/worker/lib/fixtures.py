"""
Fallback-фикстуры для worker'а, если ``packages/crm-connectors`` недоступен
или ``MockCRMConnector`` ещё не реализовал нужный метод.

Содержит детерминированные генераторы (random.Random со seed) набора:
- 100 deals
- 150 contacts
- 30 companies
- 12 crm_users
- 4 pipelines × ~6 stages
- 50 calls
- 120 messages

Используется ``trial_export`` для MVP-режима (см. ``worker/jobs/export.py``).
Также может использоваться тестами QA, когда CRM-пакет выключен из docker-compose.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

_RNG_SEED = 20260418  # детерминированность для тестов QA

_FIRST_NAMES = [
    "Иван", "Алексей", "Мария", "Светлана", "Олег",
    "Дмитрий", "Анна", "Наталья", "Павел", "Екатерина",
    "Сергей", "Виктория",
]
_LAST_NAMES = [
    "Петров", "Смирнов", "Иванов", "Кузнецов", "Попова",
    "Соколов", "Михайлов", "Новикова", "Фёдоров", "Морозов",
]
_COMPANY_SUFFIX = ["ООО", "АО", "ИП", "ПАО"]
_COMPANY_NAMES = [
    "Гелиос", "Север-Трейд", "ПромТех", "Вектор-М", "Квант",
    "Эталон", "Прогресс", "Сириус", "Аврора", "Альянс",
]
_PIPELINES = [
    "Продажи — Москва",
    "Продажи — Регионы",
    "Клиенты B2B",
    "Клиенты B2C",
]
_STAGE_NAMES = [
    "Новая заявка",
    "Первичный контакт",
    "Квалификация",
    "Презентация",
    "Оффер",
    "Переговоры",
    "Успешно",
    "Закрыто и не реализовано",
]


@dataclass
class SyntheticFixtures:
    """Набор синтетических данных, достаточный для MVP-дашборда."""

    pipelines: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)
    crm_users: list[dict[str, Any]] = field(default_factory=list)
    companies: list[dict[str, Any]] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    deals: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


def _full_name(rng: random.Random) -> str:
    return f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"


def _company_name(rng: random.Random, idx: int) -> str:
    suffix = rng.choice(_COMPANY_SUFFIX)
    core = _COMPANY_NAMES[idx % len(_COMPANY_NAMES)]
    tail = (idx // len(_COMPANY_NAMES)) + 1
    return f"{suffix} «{core}-{tail}»"


def generate_synthetic_fixtures(
    *,
    deals_count: int = 100,
    contacts_count: int = 150,
    companies_count: int = 30,
    users_count: int = 12,
    calls_count: int = 50,
    messages_count: int = 120,
    seed: int = _RNG_SEED,
) -> SyntheticFixtures:
    """
    Собрать согласованный набор фикстур.

    Связи между сущностями (deal → pipeline/stage/contact/company/user) —
    консистентны, id'шки ссылочны внутри набора.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    out = SyntheticFixtures()

    # Pipelines + Stages ----------------------------------------------------
    stage_target = 25
    stages_left = stage_target
    for p_idx, name in enumerate(_PIPELINES):
        out.pipelines.append(
            {
                "external_id": f"ext-pipe-{p_idx}",
                "name": name,
                "is_default": p_idx == 0,
            }
        )
        per_pipe = min(7, stages_left)
        if p_idx == len(_PIPELINES) - 1:
            per_pipe = max(stages_left, 1)
        for s_idx in range(per_pipe):
            stage_name = _STAGE_NAMES[s_idx % len(_STAGE_NAMES)]
            kind = (
                "won"
                if "Успешно" in stage_name
                else "lost"
                if "не реализовано" in stage_name
                else "open"
            )
            out.stages.append(
                {
                    "external_id": f"ext-stage-{p_idx}-{s_idx}",
                    "pipeline_ext_id": f"ext-pipe-{p_idx}",
                    "name": stage_name,
                    "sort_order": s_idx,
                    "kind": kind,
                }
            )
            stages_left -= 1
        if stages_left <= 0:
            break

    # CRM Users -------------------------------------------------------------
    for u_idx in range(users_count):
        out.crm_users.append(
            {
                "external_id": f"ext-user-{u_idx}",
                "full_name": _full_name(rng),
                "role": "sales" if u_idx > 0 else "lead",
                "is_active": True,
            }
        )

    # Companies -------------------------------------------------------------
    for c_idx in range(companies_count):
        out.companies.append(
            {
                "external_id": f"ext-company-{c_idx}",
                "name": _company_name(rng, c_idx),
            }
        )

    # Contacts --------------------------------------------------------------
    for c_idx in range(contacts_count):
        out.contacts.append(
            {
                "external_id": f"ext-contact-{c_idx}",
                "full_name": _full_name(rng),
                "responsible_user_ext": f"ext-user-{c_idx % users_count}",
                "created_at": (now - timedelta(days=rng.randint(0, 90))).isoformat(),
            }
        )

    # Deals -----------------------------------------------------------------
    stages_count = len(out.stages)
    for d_idx in range(deals_count):
        roll = rng.random()
        if roll < 0.60:
            status = "open"
            closed = None
        elif roll < 0.85:
            status = "won"
            closed = (now - timedelta(days=rng.randint(1, 30))).isoformat()
        else:
            status = "lost"
            closed = (now - timedelta(days=rng.randint(1, 30))).isoformat()

        stage = out.stages[rng.randrange(stages_count)]
        out.deals.append(
            {
                "external_id": f"ext-deal-{d_idx}",
                "name": f"Сделка #{d_idx + 1}",
                "pipeline_ext_id": stage["pipeline_ext_id"],
                "stage_ext_id": stage["external_id"],
                "status": status,
                "responsible_user_ext": f"ext-user-{rng.randrange(users_count)}",
                "contact_ext": f"ext-contact-{rng.randrange(contacts_count)}",
                "company_ext": f"ext-company-{rng.randrange(companies_count)}",
                "price_cents": rng.randint(10_000, 500_000) * 100,
                "currency": "RUB",
                "created_at_external": (now - timedelta(days=rng.randint(0, 60))).isoformat(),
                "closed_at_external": closed,
            }
        )

    # Calls -----------------------------------------------------------------
    for c_idx in range(calls_count):
        deal = out.deals[rng.randrange(deals_count)]
        out.calls.append(
            {
                "external_id": f"ext-call-{c_idx}",
                "deal_ext": deal["external_id"],
                "user_ext": deal["responsible_user_ext"],
                "direction": "in" if rng.random() < 0.5 else "out",
                "duration_sec": rng.randint(20, 900),
                "result": rng.choice(["ok", "missed", "no_answer"]),
                "started_at_external": (now - timedelta(days=rng.randint(0, 60),
                                                        hours=rng.randint(0, 23))).isoformat(),
            }
        )

    # Messages --------------------------------------------------------------
    for m_idx in range(messages_count):
        deal = out.deals[rng.randrange(deals_count)]
        out.messages.append(
            {
                "external_id": f"ext-msg-{m_idx}",
                "deal_ext": deal["external_id"],
                "author_kind": rng.choice(["user", "client"]),
                "text": f"Mock-сообщение {m_idx + 1}",
                "channel": rng.choice(["whatsapp", "telegram", "site"]),
                "sent_at_external": (now - timedelta(days=rng.randint(0, 30))).isoformat(),
            }
        )

    return out


def try_load_mock_connector_fixtures() -> SyntheticFixtures | None:
    """
    Попытаться использовать ``packages/crm-connectors`` ``MockCRMConnector``.

    Возвращает ``None``, если пакет недоступен (типично в тестах ранних wave'ов).
    В MVP worker не требует этого — ``trial_export`` генерит данные сам.
    """
    try:  # pragma: no cover — зависит от наличия пакета в PYTHONPATH
        from crm_connectors.mock import MockCRMConnector  # type: ignore

        MockCRMConnector()  # валидируем импорт
        # Подробная адаптация форматов — отдельная задача (CR к CRM); для MVP
        # заглушаем возвратом None, чтобы trial_export пошёл через синтетику.
        return None
    except Exception:
        return None


__all__ = [
    "SyntheticFixtures",
    "generate_synthetic_fixtures",
    "try_load_mock_connector_fixtures",
]
