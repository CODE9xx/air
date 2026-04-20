"""ck_job_kind: добавить pull_amocrm_core (Task #52.2 / Bug A).

Revision ID: 0003_ck_job_kind_pull_amocrm_core
Revises: 0002_amocrm_external_button
Create Date: 2026-04-20

Контекст
--------
0001_initial_main создал `jobs.ck_job_kind` через
``MainBase.metadata.create_all()``. На тот момент enum ``JobKind`` не
содержал значение ``pull_amocrm_core`` — этот kind был добавлен в
маппинг ``JOB_KIND_TO_QUEUE`` (``apps/api/app/core/jobs.py``) и в
``worker.jobs.crm_pull`` позже, без соответствующего обновления CHECK
constraint.

Симптом (Task #52.1A retry, live-прогон):
- callback после успешной авторизации amoCRM вызывает
  ``enqueue("pull_amocrm_core", …)``;
- INSERT в ``jobs`` падает с
  ``IntegrityError: new row … violates check constraint "ck_job_kind"``;
- bootstrap_tenant_schema job уже запланирован, но живой pull не
  стартует.

Фикс
----
Drop + recreate ``ck_job_kind`` с полным перечнем валидных kind'ов,
включая ``pull_amocrm_core``. Значения хардкодятся строковым литералом
в миграции — это детерминирует upgrade/downgrade и не зависит от
будущих эволюций ``JobKind``. Если в enum добавят новое значение, его
нужно будет вводить отдельной миграцией (тот же паттерн).

Invariant, который мы сохраняем: неизвестные kind'ы по-прежнему
отклоняются constraint'ом — это часть контракта (см. тесты job kinds).

Безопасность
------------
DDL идемпотентна в пределах одного head'а; повторный прогон не нужен
(alembic сам ведёт учёт через ``alembic_version``). Миграция не
трогает данные в ``jobs``: drop check → create check со супер-множеством
старого множества значений. Старые строки проходят новый CHECK
автоматически.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers.
revision: str = "0003_ck_job_kind_pull_amocrm_core"
down_revision: Union[str, None] = "0002_amocrm_external_button"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Полный список валидных job kinds после этой миграции. Добавляется
# только `pull_amocrm_core` — остальные значения идентичны снапшоту
# `JobKind` на момент 0001_initial_main.
_KINDS_AFTER: tuple[str, ...] = (
    "fetch_crm_data",
    "normalize_tenant_data",
    "refresh_token",
    "build_export_zip",
    "run_audit_report",
    "analyze_conversation",
    "extract_patterns",
    "anonymize_artifact",
    "retention_warning",
    "retention_read_only",
    "retention_delete",
    "delete_connection_data",
    "recalc_balance",
    "issue_invoice",
    "bootstrap_tenant_schema",
    "pull_amocrm_core",
)

# Снапшот kind'ов на момент до этой миграции — используется в downgrade(),
# чтобы вернуть CHECK к исходному состоянию.
_KINDS_BEFORE: tuple[str, ...] = tuple(k for k in _KINDS_AFTER if k != "pull_amocrm_core")


def _in_list(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"kind IN ({quoted})"


def upgrade() -> None:
    # В Postgres drop+create — атомарный DDL внутри транзакции Alembic.
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint("ck_job_kind", "jobs", _in_list(_KINDS_AFTER))


def downgrade() -> None:
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint("ck_job_kind", "jobs", _in_list(_KINDS_BEFORE))
