"""
Анонимайзер PII для AI-аналитики Code9 Analytics.

Применяется перед сохранением результатов LLM в ``ai_conversation_scores``
и ``ai_research_patterns`` согласно ``docs/ai/ANONYMIZER_RULES.md``.

Основные правила:
- Regex-блэклист: email, телефон RU/EN, ИНН (10/12 цифр с валидацией контрольной
  суммы для 10-значного), паспорт РФ, номер кредитной карты (Luhn), IP-адрес (v4).
- Вайтлист: категориальные поля (industry, objection_type и пр.) — не маскируются.
- Замена вида ``[EMAIL_1]``, ``[PHONE_RU_1]`` и т.д.
- ``privacy_risk`` — low / medium / high; ``should_store`` — bool.
- ``sample_size``: если после замен текст < 10 символов — ``should_store=False``.

Интерфейс:
    anonymize(text: str, *, workspace_id: str = "") -> AnonymizedResult
    build_research_pattern(scores, industry) -> ResearchPattern | None

CR-08 (QA, 2026-04-18): P0-блокер для AC-10. Создано Lead Architect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Типы результата
# ---------------------------------------------------------------------------

PrivacyRisk = Literal["low", "medium", "high"]


@dataclass
class Replacement:
    """Одна замена PII в тексте."""

    kind: str          # EMAIL, PHONE_RU, PHONE_EN, INN, PASSPORT, CARD, IP
    original: str      # оригинальное значение (не логировать!)
    placeholder: str   # итоговая метка, напр. [EMAIL_1]
    start: int         # позиция в исходном тексте
    end: int


@dataclass
class AnonymizedResult:
    """
    Результат анонимизации одного фрагмента текста.

    Поддерживает tuple-распаковку для обратной совместимости с тестами:
        result, risk = anonymize(text)
    """

    text: str
    replacements: list[Replacement] = field(default_factory=list)
    privacy_risk: PrivacyRisk = "low"
    should_store: bool = True

    def __iter__(self):
        """Tuple-распаковка: ``text, privacy_risk = anonymize(...)``."""
        yield self.text
        yield self.privacy_risk


# ---------------------------------------------------------------------------
# Паттерны PII
# ---------------------------------------------------------------------------

# Email
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Телефон RU: +7 / 8 + 10 цифр в различных форматах
_RE_PHONE_RU = re.compile(
    r"(?:\+7|8)[\s\-]?\(?[0-9]{3}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}"
)

# Телефон EN (US): +1 + 10 цифр
_RE_PHONE_EN = re.compile(
    r"\+1[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}"
)

# ИНН: ровно 10 или 12 цифр на границах слова
_RE_INN = re.compile(r"\b(\d{10}|\d{12})\b")

# Паспорт РФ: XXXX XXXXXX (серия 4 цифры, номер 6 цифр, с возможным пробелом)
_RE_PASSPORT = re.compile(r"\b\d{4}\s?\d{6}\b")

# IP-адрес v4
_RE_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Кредитная карта: 16 цифр (группы по 4, разделены пробелом или тире, или слитно)
_RE_CARD = re.compile(
    r"\b(?:\d{4}[\s\-]){3}\d{4}\b"
    r"|\b\d{16}\b"
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _luhn_check(number: str) -> bool:
    """Проверка алгоритмом Луна. Возвращает True, если число проходит."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _inn_valid_10(digits: str) -> bool:
    """Контрольная сумма ИНН 10 цифр (юрлица)."""
    if len(digits) != 10:
        return False
    coeffs = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    s = sum(c * int(d) for c, d in zip(coeffs, digits[:9]))
    return int(digits[9]) == (s % 11) % 10


def _inn_valid_12(digits: str) -> bool:
    """Контрольная сумма ИНН 12 цифр (физлица)."""
    if len(digits) != 12:
        return False
    c1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    c2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    s1 = sum(c * int(d) for c, d in zip(c1, digits[:10]))
    s2 = sum(c * int(d) for c, d in zip(c2, digits[:11]))
    return (int(digits[10]) == (s1 % 11) % 10) and (int(digits[11]) == (s2 % 11) % 10)


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------

def anonymize(text: str, *, workspace_id: str = "") -> AnonymizedResult:
    """
    Анонимизировать PII в переданном тексте.

    Аргументы:
        text: входной текст (ответ LLM или фрагмент разговора).
        workspace_id: идентификатор воркспейса (для будущего аудита, в MVP не используется).

    Возвращает:
        AnonymizedResult с маскированным текстом, списком замен,
        уровнем риска и флагом ``should_store``.
    """
    replacements: list[Replacement] = []
    # Счётчики по типу для нумерации плейсхолдеров
    counters: dict[str, int] = {}

    # Список правил: (kind, compiled_regex, validator_fn | None, placeholder_prefix)
    rules: list[tuple[str, re.Pattern, object]] = [
        ("CARD",      _RE_CARD,      _luhn_check),
        ("EMAIL",     _RE_EMAIL,     None),
        ("PHONE_RU",  _RE_PHONE_RU,  None),
        ("PHONE_EN",  _RE_PHONE_EN,  None),
        ("INN",       _RE_INN,       lambda s: _inn_valid_10(s) or _inn_valid_12(s)),
        ("PASSPORT",  _RE_PASSPORT,  None),
        ("IP",        _RE_IP,        None),
    ]

    # Строим список всех совпадений (span → kind, оригинал, валид)
    findings: list[tuple[int, int, str, str]] = []  # (start, end, kind, original)

    for kind, pattern, validator in rules:
        for m in pattern.finditer(text):
            raw = m.group()
            digits_only = re.sub(r"\D", "", raw)
            # Для ИНН применяем контрольную сумму
            if kind == "INN" and validator is not None:
                if not validator(digits_only):  # type: ignore[call-arg]
                    continue
            # Для карты — Luhn
            elif kind == "CARD" and validator is not None:
                if not _luhn_check(digits_only):
                    continue
            findings.append((m.start(), m.end(), kind, raw))

    # Сортируем по позиции, убираем перекрытия (первый приоритет = больший span)
    findings.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    non_overlapping: list[tuple[int, int, str, str]] = []
    last_end = -1
    for start, end, kind, raw in findings:
        if start >= last_end:
            non_overlapping.append((start, end, kind, raw))
            last_end = end

    # Строим новый текст и список Replacement
    result_parts: list[str] = []
    prev = 0
    for start, end, kind, raw in non_overlapping:
        counters[kind] = counters.get(kind, 0) + 1
        placeholder = f"[{kind}_{counters[kind]}]"
        result_parts.append(text[prev:start])
        result_parts.append(placeholder)
        replacements.append(Replacement(
            kind=kind,
            original=raw,
            placeholder=placeholder,
            start=start,
            end=end,
        ))
        prev = end
    result_parts.append(text[prev:])
    anonymized_text = "".join(result_parts)

    # ---------------------------------------------------------------------------
    # Определяем privacy_risk и should_store
    # ---------------------------------------------------------------------------
    found_kinds = {r.kind for r in replacements}
    has_card = "CARD" in found_kinds
    has_passport = "PASSPORT" in found_kinds
    pii_type_count = len(found_kinds)

    if has_card or has_passport or pii_type_count >= 3:
        risk: PrivacyRisk = "high"
        should_store = False
    elif pii_type_count >= 1:
        risk = "medium"
        should_store = True
    else:
        risk = "low"
        should_store = True

    # Минимальный sample_size: если текст после замен слишком короткий — не сохраняем
    if len(anonymized_text.strip()) < 10:
        should_store = False

    return AnonymizedResult(
        text=anonymized_text,
        replacements=replacements,
        privacy_risk=risk,
        should_store=should_store,
    )


# ---------------------------------------------------------------------------
# build_research_pattern — агрегация скоров в паттерн для ai_research_patterns
# ---------------------------------------------------------------------------

@dataclass
class ResearchPattern:
    """Агрегированный паттерн для сохранения в ``ai_research_patterns``."""

    industry: str
    sample_size: int
    objection_types: dict[str, int]
    avg_confidence: float
    privacy_risk: PrivacyRisk


def build_research_pattern(
    scores: list[dict],
    industry: str,
) -> ResearchPattern | None:
    """
    Агрегировать список скоров разговоров в исследовательский паттерн.

    Возвращает None, если:
    - ``len(scores) < 10`` (риск re-identification по ANONYMIZER_RULES.md §3);
    - после анонимизации хоть одного скора ``privacy_risk == high``.

    Аргументы:
        scores: список dict-объектов ``ai_conversation_scores`` (без raw PII).
        industry: индустрия workspace (из вайтлиста ANONYMIZER_RULES.md §2).

    Возвращает ResearchPattern или None.
    """
    if len(scores) < 10:
        return None

    objection_counts: dict[str, int] = {}
    confidences: list[float] = []
    overall_risk: PrivacyRisk = "low"

    for score in scores:
        # Проверяем текстовые поля на PII
        raw_text = score.get("summary") or score.get("objection_text") or ""
        if raw_text:
            result = anonymize(str(raw_text))
            if result.privacy_risk == "high":
                return None  # небезопасно агрегировать
            if result.privacy_risk == "medium" and overall_risk == "low":
                overall_risk = "medium"

        objection = score.get("objection_type")
        if objection:
            objection_counts[objection] = objection_counts.get(objection, 0) + 1

        conf = score.get("confidence")
        if conf is not None:
            try:
                confidences.append(float(conf))
            except (TypeError, ValueError):
                pass

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return ResearchPattern(
        industry=industry,
        sample_size=len(scores),
        objection_types=objection_counts,
        avg_confidence=round(avg_conf, 4),
        privacy_risk=overall_risk,
    )


__all__ = [
    "anonymize",
    "build_research_pattern",
    "AnonymizedResult",
    "Replacement",
    "ResearchPattern",
    "PrivacyRisk",
]
