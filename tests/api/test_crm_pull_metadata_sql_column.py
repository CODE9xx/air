"""
Regression guard for Bug G (Task #52.3G).

Предыстория
-----------
2026-04-21, после фикса Bug F (Task #52.3F), recovery коннекта
``1ede9725-4b4e-4157-8a12-a8ac9c67f274`` прошло все фазы sync'а
(``pipelines=1, stages=7, crm_users=2, contacts=0, deals=0``
успешно залиты в tenant schema ``crm_amo_34a9d7aa``), но на
финальном ``UPDATE public.crm_connections SET metadata_json = ...``
упало::

    psycopg2.errors.UndefinedColumn:
        column "metadata_json" does not exist
    SQL: UPDATE crm_connections SET
           last_sync_at = NOW(),
           updated_at = NOW(),
           metadata_json = COALESCE(metadata_json, '{}'::jsonb)
             || CAST(:patch AS JSONB)
         WHERE id = CAST(:cid AS UUID)

Первопричина
------------
Реальное имя колонки в БД — ``metadata`` (JSONB). Python-атрибут
в ORM переименован, потому что SQLAlchemy резервирует ``metadata``
на declarative base::

    # apps/api/app/db/models/__init__.py
    class CrmConnection(Base):
        ...
        metadata_json = Column("metadata", JSONB, nullable=False,
                               server_default="{}")

ORM-доступ (``conn.metadata_json = {...}``) корректно переводится в
``UPDATE ... metadata = ...``. Но ``worker/jobs/crm_pull.py`` использует
raw ``text()``-SQL, который обходит ORM-маппинг и ожидает реальное имя
колонки. В багнутой версии там стоял Python-атрибут ``metadata_json`` —
соответственно, PostgreSQL отвечал ``UndefinedColumn``.

Фикс
----
В ``apps/worker/worker/jobs/crm_pull.py`` в ``text()`` UPDATE
заменено ``metadata_json`` → ``metadata`` (оба вхождения в той же
строке — target column и argument в COALESCE).

Что покрывают тесты
-------------------
1. Положительный контракт: модуль содержит UPDATE c корректным
   именем колонки ``metadata = COALESCE(metadata, ...)``.
2. Регресс-guard: **ни одна** raw-SQL-литералка в модуле не ссылается
   на несуществующую колонку ``metadata_json`` (ни как target, ни как
   argument). Docstring'и / комментарии с упоминанием ``metadata_json``
   как ORM-атрибута разрешены.
3. Soft-guard: allow-list явных «легитимных» упоминаний (docstring,
   pointer на ORM) — чтобы тест не падал на осмысленных объяснениях,
   но падал на реально опасных raw-SQL-паттернах.

Почему source-level, а не integration
-------------------------------------
Прод-Postgres в test-контейнере недоступен. Source-level regex-guard
ловит конкретную багнутую конструкцию (``"... metadata_json = COALESCE(
metadata_json, ...)"``) — именно тот паттерн, который PostgreSQL
отверг в продакшене.

Безопасность теста
------------------
Не использует DSN, БД, sitedata. Только чтение исходников.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

# Worker-модуль живёт в ``apps/worker/worker/*``; в api-контейнере
# этот путь не на ``sys.path``, поэтому вставляем его явно — тот же
# приём, что и в ``test_amocrm_worker_credentials.py``.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_SRC = _REPO_ROOT / "apps" / "worker"
if _WORKER_SRC.is_dir() and str(_WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKER_SRC))

from worker.jobs import crm_pull  # noqa: E402  (sys.path hack above)


def _module_source() -> str:
    return inspect.getsource(crm_pull)


def test_crm_pull_update_uses_real_metadata_column_name() -> None:
    """Positive contract: модуль содержит UPDATE c правильным именем колонки.

    Ожидаемая SQL-фраза::

        metadata = COALESCE(metadata, '{}'::jsonb)

    (пробелы допустимо пропускать; JSONB-кастинг обязателен, иначе
    COALESCE вернёт text и PostgreSQL упадёт на ``||`` без CAST.)
    """
    src = _module_source()
    pat = re.compile(
        r"metadata\s*=\s*COALESCE\(\s*metadata\s*,\s*'\{\}'::jsonb\s*\)",
    )
    assert pat.search(src), (
        "Expected UPDATE crm_connections SET ... metadata = "
        "COALESCE(metadata, '{}'::jsonb) in apps/worker/worker/jobs/crm_pull.py; "
        "либо SQL был переписан (обнови тест), либо фикс Bug G откачен."
    )


def test_no_raw_sql_references_nonexistent_metadata_json_column() -> None:
    """Regression guard: ни одна SQL-литералка не обращается к колонке ``metadata_json``.

    Проверяется именно **паттерн raw-SQL** — т.е. ``metadata_json`` внутри
    кавычек PLUS участие в присваивании/сравнении/COALESCE (``=``,
    ``::jsonb``, ``COALESCE(`` в ближайших символах).

    Docstring'и и комментарии, где упоминается Python-атрибут
    ``CrmConnection.metadata_json``, разрешены.
    """
    src = _module_source()

    # 1) Жёсткий паттерн: багнутая конструкция 1-в-1.
    hard_bug = re.compile(
        r"\"[^\"\n]*\bmetadata_json\s*=\s*COALESCE\s*\(\s*metadata_json[^\"\n]*\"",
    )
    hits = hard_bug.findall(src)
    assert not hits, (
        "Bug G regression: найдена багнутая raw-SQL конструкция "
        "`\"... metadata_json = COALESCE(metadata_json, ...)\"` — "
        f"колонка metadata_json не существует в БД. Hits: {hits!r}"
    )

    # 2) Общий guard: любое присваивание ``metadata_json = `` внутри
    #    строкового SQL-литерала.
    sql_assign = re.compile(
        r"\"[^\"\n]*\bmetadata_json\s*=\s*(?!Column)[^\"\n]*\"",
    )
    hits2 = sql_assign.findall(src)
    assert not hits2, (
        "Bug G regression: raw-SQL литерал присваивает метаданные в "
        "несуществующую колонку ``metadata_json``. Реальная колонка — "
        f"``metadata``. Hits: {hits2!r}"
    )


def test_metadata_json_mentions_are_only_in_docstring_or_comments() -> None:
    """Belt-and-suspenders: все упоминания ``metadata_json`` в crm_pull
    должны быть только в строках docstring'а или в ``#``-комментариях.

    Мы НЕ допускаем появления голого токена ``metadata_json`` как Python-
    идентификатора в ``.execute(text(...))``-context'ах в этом модуле.
    Если кому-то нужно писать per-connection metadata через SQLAlchemy
    ORM — пусть делает ``conn.metadata_json = ...`` (там attribute-map
    корректно разворачивается в column ``metadata``), не через raw SQL.
    """
    src_lines = _module_source().splitlines()
    offending: list[tuple[int, str]] = []
    in_docstring = False
    docstring_delim = re.compile(r'(?:^|[^"])(""")')
    for i, line in enumerate(src_lines, 1):
        # Примитивный трекер: считаем кол-во `"""` в строке; нечётное — флип.
        triple_count = line.count('"""')
        was_in = in_docstring
        if triple_count % 2 == 1:
            in_docstring = not in_docstring
        is_docline = was_in or in_docstring or docstring_delim.search(line)
        if "metadata_json" not in line:
            continue
        stripped = line.lstrip()
        # Разрешённые контексты: docstring (любой кусок), или строка начинается с '#'.
        if is_docline or stripped.startswith("#"):
            continue
        # Разрешённые ORM-атрибут/комментарии-внутри-строк типа
        # 'CrmConnection.metadata_json' в ``.py`` файлах скорее всего будут
        # в docstring'е или комментарии, покрытых выше. Всё остальное — баг.
        offending.append((i, line.rstrip()))
    assert not offending, (
        "Bug G regression: найдены упоминания ``metadata_json`` вне "
        "docstring'ов/комментариев в apps/worker/worker/jobs/crm_pull.py:\n"
        + "\n".join(f"  L{i}: {ln!r}" for i, ln in offending)
    )
