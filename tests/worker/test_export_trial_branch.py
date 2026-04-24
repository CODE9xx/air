"""
Unit tests for ``worker.jobs.export.build_export_zip`` (Task #52.5).

Фиксирует контракт dispatching:
  - ``build_export_zip(connection_id, trial=True, ...)``  → ``trial_export``
  - ``build_export_zip(connection_id, trial=False, ...)`` → ``full_export``
  - ``build_export_zip(connection_id, ...)``              → ``full_export``
    (default trial=False — legacy-compat для jobs, поставленных до деплоя).
  - ``trial: bool`` keyword-only → RQ ``enqueue_call(kwargs=payload)``
    не попадёт на позиционный arg (что сломало бы Bug D fix из #52.3D).

Не требует живого DB/Redis: мы патчим ``trial_export``/``full_export``
прямо в модуле.
"""
from __future__ import annotations

import inspect
from unittest.mock import patch


def test_build_export_zip_trial_true_calls_trial_export():
    from worker.jobs import export as mod

    with patch.object(mod, "trial_export", return_value={"rows_exported": 100}) as mt, \
         patch.object(mod, "full_export", return_value={"rows_exported": 0}) as mf:
        result = mod.build_export_zip(
            connection_id="conn-id-42",
            trial=True,
            job_row_id="row-1",
        )

    mt.assert_called_once_with(connection_id="conn-id-42", job_row_id="row-1")
    mf.assert_not_called()
    assert result == {"rows_exported": 100}


def test_build_export_zip_legacy_mode_trial_calls_trial_export():
    """Legacy jobs may have payload {"mode": "trial"} from pre-#52.5 UI code.

    build_export_zip must tolerate that payload so old RQ jobs can be retried
    instead of failing before mark_job_failed can update public.jobs.
    """
    from worker.jobs import export as mod

    with patch.object(mod, "trial_export", return_value={"rows_exported": 100}) as mt, \
         patch.object(mod, "full_export", return_value={"rows_exported": 0}) as mf:
        result = mod.build_export_zip(
            connection_id="conn-id-42",
            mode="trial",
            job_row_id="row-1",
        )

    mt.assert_called_once_with(connection_id="conn-id-42", job_row_id="row-1")
    mf.assert_not_called()
    assert result == {"rows_exported": 100}


def test_build_export_zip_trial_false_calls_full_export():
    from worker.jobs import export as mod

    with patch.object(mod, "trial_export", return_value={"rows_exported": 100}) as mt, \
         patch.object(mod, "full_export", return_value={"rows_exported": 0}) as mf:
        result = mod.build_export_zip(
            connection_id="conn-id-42",
            trial=False,
            job_row_id="row-1",
        )

    mt.assert_not_called()
    mf.assert_called_once_with(connection_id="conn-id-42", job_row_id="row-1")
    assert result == {"rows_exported": 0}


def test_build_export_zip_default_is_non_trial_preserves_legacy_behavior():
    """
    Default trial=False — сохраняет старое поведение build_export_zip.

    Важно для jobs, которые уже в очереди RQ на момент деплоя фикса:
    их payload не содержит ``trial`` (до #52.5 такого ключа не было).
    Они должны продолжать работать через full_export, без TypeError.
    """
    from worker.jobs import export as mod

    with patch.object(mod, "trial_export") as mt, \
         patch.object(mod, "full_export", return_value={"rows_exported": 0}) as mf:
        result = mod.build_export_zip(connection_id="conn-id-42")

    mt.assert_not_called()
    mf.assert_called_once_with(connection_id="conn-id-42", job_row_id=None)
    assert result == {"rows_exported": 0}


def test_build_export_zip_signature_accepts_trial_kwarg():
    """
    Regression для Bug D (Task #52.3D): сигнатура build_export_zip
    обязана принимать ``trial`` как keyword-only с default=False.

    Если этот тест падает — либо фикс Task #52.5 откатили, либо
    кто-то поменял kind trial вручную (позиционно) — оба варианта
    ломают RQ enqueue_call(kwargs={"trial": True, ...}).
    """
    from worker.jobs import export as mod

    sig = inspect.signature(mod.build_export_zip)
    assert "trial" in sig.parameters, (
        "build_export_zip должен принимать trial kwarg (Task #52.5)"
    )
    trial_param = sig.parameters["trial"]
    assert trial_param.default is False, (
        "trial default должен быть False, иначе legacy-вызовы без kwarg "
        "пойдут в trial_export и перезатрут production-данные."
    )
    assert trial_param.kind == inspect.Parameter.KEYWORD_ONLY, (
        "trial обязан быть keyword-only — worker-функции все вызываются "
        "через enqueue_call(kwargs=payload), позиционных args не бывает."
    )


def test_build_export_zip_signature_keeps_connection_id_required():
    """Negative guard: connection_id должен остаться обязательным
    позиционным/keyword-поддерживаемым параметром (чтобы RQ передал
    payload['connection_id'] корректно)."""
    from worker.jobs import export as mod

    sig = inspect.signature(mod.build_export_zip)
    assert "connection_id" in sig.parameters
    cid = sig.parameters["connection_id"]
    assert cid.default is inspect.Parameter.empty, (
        "connection_id должен быть required — без него job бессмысленный."
    )


def test_build_export_zip_trial_propagates_job_row_id():
    """Контракт: trial-ветка передаёт ``job_row_id`` в trial_export
    без изменений. Без этого mark_job_succeeded не обновит public.jobs
    и UI останется в status='queued' навсегда."""
    from worker.jobs import export as mod

    with patch.object(mod, "trial_export", return_value={}) as mt, \
         patch.object(mod, "full_export"):
        mod.build_export_zip(
            connection_id="conn-id",
            trial=True,
            job_row_id="specific-row-xyz",
        )

    call_kwargs = mt.call_args.kwargs
    assert call_kwargs.get("job_row_id") == "specific-row-xyz", (
        f"trial-ветка потеряла job_row_id: {call_kwargs!r}"
    )
