"""
Тесты инварианта ``JobKind`` ↔ ``JOB_KIND_TO_QUEUE`` ↔ миграция ck_job_kind.

Bug A (Task #52.2, обнаружен в live-прогоне Task #52.1A):
  ``pull_amocrm_core`` присутствует в ``JOB_KIND_TO_QUEUE``, функция лежит
  в ``worker.jobs.crm_pull``, но в ORM-enum ``JobKind`` этого значения
  не было — ``ck_job_kind`` CHECK constraint отклонял INSERT при enqueue
  после успешного amoCRM-callback.

Эти тесты фиксируют три условия:
  1. ``PULL_AMOCRM_CORE`` есть в ``JobKind`` enum.
  2. Маппинг ``JOB_KIND_TO_QUEUE["pull_amocrm_core"] == "crm"``.
  3. Маппинг ``JOB_KIND_TO_MODULE["pull_amocrm_core"] == "crm_pull"``.
  4. Неизвестный kind по-прежнему отклоняется ``queue_for_kind``.
  5. Каждый ключ в ``JOB_KIND_TO_QUEUE`` покрыт enum'ом (для защиты
     от регрессии — если kind в маппинге, он обязан быть и в enum,
     иначе ``ck_job_kind`` снова отклонит INSERT).
"""
from __future__ import annotations

import pytest

from app.core.jobs import JOB_KIND_TO_MODULE, JOB_KIND_TO_QUEUE, queue_for_kind
from app.db.models.enums import JobKind


def test_pull_amocrm_core_in_jobkind_enum():
    assert JobKind.PULL_AMOCRM_CORE.value == "pull_amocrm_core"
    assert "pull_amocrm_core" in {k.value for k in JobKind}


def test_pull_amocrm_core_mapped_to_crm_queue():
    assert JOB_KIND_TO_QUEUE.get("pull_amocrm_core") == "crm"


def test_pull_amocrm_core_module_override_present():
    # JOB_KIND_TO_MODULE нужен, потому что функция лежит не в worker.jobs.crm
    # (одноимённый модуль), а в worker.jobs.crm_pull.
    assert JOB_KIND_TO_MODULE.get("pull_amocrm_core") == "crm_pull"


def test_queue_for_kind_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown job kind"):
        queue_for_kind("definitely_not_a_real_kind")


def test_every_queue_map_kind_exists_in_enum():
    """Защита от регрессии: если kind есть в JOB_KIND_TO_QUEUE, он
    обязан присутствовать в JobKind, иначе ck_job_kind снова отклонит
    INSERT после enqueue.
    """
    enum_values = {k.value for k in JobKind}
    missing = [k for k in JOB_KIND_TO_QUEUE if k not in enum_values]
    assert not missing, f"kinds in queue map but missing from JobKind enum: {missing}"


def test_every_enum_kind_has_queue():
    """Обратная проверка: каждый объявленный JobKind должен иметь
    соответствие в JOB_KIND_TO_QUEUE, иначе ``enqueue()`` этот kind
    отвергнет как Unknown.
    """
    unmapped = [k.value for k in JobKind if k.value not in JOB_KIND_TO_QUEUE]
    assert not unmapped, f"JobKind values without queue mapping: {unmapped}"


def test_jobkind_values_are_snake_case():
    """Все значения kind'ов — snake_case, без пробелов/дефисов/юникода."""
    import re
    pat = re.compile(r"^[a-z][a-z0-9_]*$")
    bad = [k.value for k in JobKind if not pat.fullmatch(k.value)]
    assert not bad, f"JobKind values must be snake_case: {bad}"
