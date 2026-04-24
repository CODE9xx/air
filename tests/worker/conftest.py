"""
Conftest для worker-тестов.

Добавляет ``apps/worker`` в ``sys.path``, чтобы ``import worker.jobs.*``
работал без установки пакета в site-packages. Аналогично верхнеуровневому
tests/conftest.py для api (тот добавляет apps/api через PYTHONPATH
из docker-compose, у нас же worker-тесты могут запускаться и локально,
и в api-контейнере, где apps/worker напрямую не примонтирован).

Если тест не может импортировать worker-пакет (нет зависимостей
``sqlalchemy``/``asyncpg`` и т.п.), он пометится как collection-error,
что видно в pytest --collect-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

# tests/worker/conftest.py  →  repo root — 2 уровня вверх.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_ROOT = _REPO_ROOT / "apps" / "worker"

if _WORKER_ROOT.is_dir() and str(_WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKER_ROOT))
