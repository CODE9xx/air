from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_ai_actions_page_has_situation_builder_contract():
    source = (ROOT / "apps/web/app/[locale]/app/ai-actions/page.tsx").read_text(encoding="utf-8")

    for scenario in (
        "Выставить счет",
        "Перезвонить",
        "Получить КП",
        "Нет ответа",
        "Поговорить с живым менеджером",
    ):
        assert scenario in source

    assert "conditions" in source
    assert "actions" in source
    assert "riskMode" in source
    assert "Сообщение клиенту" in source
    assert "Реальное создание задач" in source
    assert "/export/options" in source
    assert "Работает на этапах amoCRM" in source
    assert "selectedStageIds" in source
    assert "togglePipeline" in source
    assert "stageDropdownOpen" in source
    assert "Выбрать все" in source
    assert "Убрать все" in source
    assert "filterExportOptionsByActiveExport" in source
    assert "metadata?.active_export?.pipeline_ids" in source
    assert "Показываем только воронки, выбранные в активной выгрузке amoCRM" in source
    assert "Выберите хотя бы один этап amoCRM" in source
    assert "setSaved(true)" in source
