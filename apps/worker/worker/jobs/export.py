"""
Export jobs: trial_export (mock 100 deals + ассоциированные сущности в tenant)
и full_export (заглушка с прогрессом в MVP).

trial_export реализует полноценную сид-логику: pipelines/stages/users/companies/
contacts/deals — чтобы FE/QA мог увидеть дашборды на фикстивных данных сразу
после активации подключения.
"""
from __future__ import annotations

import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from ..lib.db import sync_session
from ._common import mark_job_failed, mark_job_running, mark_job_succeeded

# Константы mock-генерации.
SOURCES = ["site", "whatsapp", "telegram", "avito", "referral", "ads", "unknown"]
PIPELINE_NAMES = [
    "Продажи — Москва",
    "Продажи — Регионы",
    "Клиенты B2B",
    "Клиенты B2C",
]
STAGE_NAMES = [
    "Новая заявка",
    "Первичный контакт",
    "Квалификация",
    "Презентация",
    "Оффер",
    "Переговоры",
    "Успешно",
    "Закрыто и не реализовано",
]


def _get_tenant_schema(connection_id: str) -> str:
    """Получить tenant_schema, подняв bootstrap при необходимости."""
    from .crm import bootstrap_tenant_schema

    with sync_session() as sess:
        row = sess.execute(
            text(
                "SELECT tenant_schema FROM crm_connections "
                "WHERE id = CAST(:cid AS UUID)"
            ),
            {"cid": connection_id},
        ).fetchone()
        if row is None:
            raise RuntimeError(f"connection {connection_id} не найден")
        schema = row[0]

    if not schema:
        bootstrap_tenant_schema(connection_id=connection_id)
        with sync_session() as sess:
            row = sess.execute(
                text(
                    "SELECT tenant_schema FROM crm_connections "
                    "WHERE id = CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            ).fetchone()
            schema = row[0] if row else None

    if not schema:
        raise RuntimeError(f"не удалось получить tenant_schema для {connection_id}")
    return schema


def _uuid() -> str:
    return str(uuid.uuid4())


def trial_export(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Сгенерировать mock-данные внутри tenant-схемы:
    - 4 pipelines, 25 stages, 12 crm_users, 30 companies, 150 contacts,
    - **100 deals** (основной deliverable по AC).
    """
    mark_job_running(job_row_id)
    try:
        schema = _get_tenant_schema(connection_id)

        # Безопасно: schema name был провалидирован при создании.
        q_schema = f'"{schema}"'

        print(f"[trial_export] schema={schema} progress=0%", flush=True)
        time.sleep(0.3)

        with sync_session() as sess:
            # Все последующие операторы — в этой схеме.
            sess.execute(text(f'SET LOCAL search_path = {q_schema}, public'))

            # ---- Pipelines + stages -----------------------------------
            pipeline_ids: list[str] = []
            for idx, pname in enumerate(PIPELINE_NAMES):
                pid = _uuid()
                pipeline_ids.append(pid)
                sess.execute(
                    text(
                        "INSERT INTO pipelines(id, external_id, name, is_default) "
                        "VALUES (CAST(:id AS UUID), :ext, :name, :def) "
                        "ON CONFLICT (external_id) DO NOTHING"
                    ),
                    {
                        "id": pid,
                        "ext": f"ext-pipe-{idx}",
                        "name": pname,
                        "def": idx == 0,
                    },
                )

            stage_pool: list[tuple[str, str]] = []  # (stage_id, pipeline_id)
            # 4 pipelines × ~6-7 stages = 25 suma (+1 на один pipeline).
            target_stages = 25
            created = 0
            for p_idx, pid in enumerate(pipeline_ids):
                per_pipe = 7 if created + 7 <= target_stages else target_stages - created
                if per_pipe <= 0:
                    break
                for s_idx in range(per_pipe):
                    sid = _uuid()
                    name = STAGE_NAMES[s_idx % len(STAGE_NAMES)]
                    kind = (
                        "won"
                        if "Успешно" in name
                        else "lost"
                        if "не реализовано" in name
                        else "open"
                    )
                    sess.execute(
                        text(
                            "INSERT INTO stages(id, external_id, pipeline_id, name, sort_order, kind) "
                            "VALUES (CAST(:id AS UUID), :ext, CAST(:pid AS UUID), :n, :o, :k) "
                            "ON CONFLICT (external_id) DO NOTHING"
                        ),
                        {
                            "id": sid,
                            "ext": f"ext-stage-{p_idx}-{s_idx}",
                            "pid": pid,
                            "n": name,
                            "o": s_idx,
                            "k": kind,
                        },
                    )
                    stage_pool.append((sid, pid))
                    created += 1
                    if created >= target_stages:
                        break

            # ---- CRM users (12) --------------------------------------
            user_ids: list[str] = []
            for u_idx in range(12):
                uid = _uuid()
                user_ids.append(uid)
                sess.execute(
                    text(
                        "INSERT INTO crm_users(id, external_id, full_name, role, is_active) "
                        "VALUES (CAST(:id AS UUID), :ext, :name, :role, TRUE) "
                        "ON CONFLICT (external_id) DO NOTHING"
                    ),
                    {
                        "id": uid,
                        "ext": f"ext-user-{u_idx}",
                        "name": f"Менеджер #{u_idx + 1}",
                        "role": "sales" if u_idx > 0 else "lead",
                    },
                )

            print(f"[trial_export] schema={schema} progress=25%", flush=True)
            time.sleep(0.3)

            # ---- Companies (30) --------------------------------------
            company_ids: list[str] = []
            for c_idx in range(30):
                cid = _uuid()
                company_ids.append(cid)
                sess.execute(
                    text(
                        "INSERT INTO companies(id, external_id, name) "
                        "VALUES (CAST(:id AS UUID), :ext, :name) "
                        "ON CONFLICT (external_id) DO NOTHING"
                    ),
                    {
                        "id": cid,
                        "ext": f"ext-company-{c_idx}",
                        "name": f"ООО «Компания #{c_idx + 1}»",
                    },
                )

            # ---- Contacts (150) --------------------------------------
            contact_ids: list[str] = []
            for c_idx in range(150):
                cid = _uuid()
                contact_ids.append(cid)
                resp = random.choice(user_ids)
                sess.execute(
                    text(
                        "INSERT INTO contacts(id, external_id, full_name, responsible_user_id) "
                        "VALUES (CAST(:id AS UUID), :ext, :name, CAST(:uid AS UUID)) "
                        "ON CONFLICT (external_id) DO NOTHING"
                    ),
                    {
                        "id": cid,
                        "ext": f"ext-contact-{c_idx}",
                        "name": f"Клиент {c_idx + 1}",
                        "uid": resp,
                    },
                )

            print(f"[trial_export] schema={schema} progress=60%", flush=True)
            time.sleep(0.3)

            # ---- Deals (100) -----------------------------------------
            now = datetime.now(timezone.utc)
            for d_idx in range(100):
                status_roll = random.random()
                if status_roll < 0.60:
                    status = "open"
                    closed = None
                elif status_roll < 0.85:
                    status = "won"
                    closed = now - timedelta(days=random.randint(1, 30))
                else:
                    status = "lost"
                    closed = now - timedelta(days=random.randint(1, 30))

                # Stage согласно pipeline'у: подбираем stage из пула.
                stage_id, pipeline_id = random.choice(stage_pool)
                price_rub = random.randint(10000, 500000)
                created_at_ext = now - timedelta(days=random.randint(0, 60))
                sess.execute(
                    text(
                        "INSERT INTO deals("
                        "  id, external_id, name, pipeline_id, stage_id, status, "
                        "  responsible_user_id, contact_id, company_id, price_cents, "
                        "  currency, created_at_external, closed_at_external"
                        ") VALUES ("
                        "  CAST(:id AS UUID), :ext, :name, CAST(:pid AS UUID), "
                        "  CAST(:sid AS UUID), :status, CAST(:uid AS UUID), "
                        "  CAST(:cid AS UUID), CAST(:coid AS UUID), :price, "
                        "  :cur, :ca, :cla"
                        ") ON CONFLICT (external_id) DO NOTHING"
                    ),
                    {
                        "id": _uuid(),
                        "ext": f"ext-deal-{d_idx}",
                        "name": f"Сделка #{d_idx + 1}",
                        "pid": pipeline_id,
                        "sid": stage_id,
                        "status": status,
                        "uid": random.choice(user_ids),
                        "cid": random.choice(contact_ids),
                        "coid": random.choice(company_ids),
                        "price": price_rub * 100,  # cents
                        "cur": "RUB",
                        "ca": created_at_ext,
                        "cla": closed,
                    },
                )

            print(f"[trial_export] schema={schema} progress=100%", flush=True)

        result = {
            "connection_id": connection_id,
            "tenant_schema": schema,
            "deals_created": 100,
            "contacts_created": 150,
            "companies_created": 30,
            "pipelines_created": len(pipeline_ids),
            "stages_created": len(stage_pool),
            "crm_users_created": len(user_ids),
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"trial_export: {exc}")
        raise


def full_export(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Полный экспорт — в MVP заглушка с прогрессом (реальная реализация — V1)."""
    mark_job_running(job_row_id)
    try:
        for progress in (0, 10, 30, 55, 80, 100):
            print(
                f"[full_export] connection={connection_id} progress={progress}%",
                flush=True,
            )
            if progress < 100:
                time.sleep(0.5)
        result = {
            "connection_id": connection_id,
            "note": "full_export — MVP stub; реальная реализация в V1",
            "rows_exported": 0,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"full_export: {exc}")
        raise


def build_export_zip(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Zip-сборка экспорта (стаб-алиас full_export)."""
    return full_export(connection_id=connection_id, job_row_id=job_row_id)
