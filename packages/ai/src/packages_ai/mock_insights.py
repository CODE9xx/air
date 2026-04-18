"""
Mock-инсайты для AI endpoints (без реального LLM).

В MVP возвращаем три детерминированных инсайта, чтобы UI мог их отрисовать.
"""
from __future__ import annotations

from typing import Any


def build_mock_insights(connection_id: str | None = None) -> list[dict[str, Any]]:
    """Три преднастроенных инсайта — заглушка для Wave 2 UI."""
    base = [
        {
            "id": "insight-abandoned-deals",
            "type": "abandoned_deals",
            "severity": "high",
            "title": "Сделки зависают на этапе 'Переговоры'",
            "description": (
                "В 34% сделок нет обновлений > 7 дней после входа на этап 'Переговоры'. "
                "Это типичная точка отвала."
            ),
            "recommendation": "Ввести обязательный follow-up через 3 дня после старта этапа.",
            "confidence": 0.72,
            "sample_size": 126,
        },
        {
            "id": "insight-missed-needs",
            "type": "missed_needs",
            "severity": "medium",
            "title": "Менеджеры пропускают выявление потребностей",
            "description": (
                "В 41% звонков отсутствует явный блок вопросов клиенту про задачи и бюджет. "
                "Это коррелирует со сниженной конверсией в договор."
            ),
            "recommendation": "Добавить чеклист 'Выявление потребностей' в скрипт первого звонка.",
            "confidence": 0.64,
            "sample_size": 210,
        },
        {
            "id": "insight-no-next-step",
            "type": "no_next_step",
            "severity": "medium",
            "title": "Нет следующего шага в 28% звонков",
            "description": (
                "По ~28% разговоров после звонка не создаётся задача с конкретной датой. "
                "Это увеличивает цикл сделки."
            ),
            "recommendation": "Ввести правило: после каждого звонка — задача с дедлайном.",
            "confidence": 0.81,
            "sample_size": 188,
        },
    ]
    # Добавляем привязку к connection_id в metadata.
    for item in base:
        item["connection_id"] = connection_id
    return base
