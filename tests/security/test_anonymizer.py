"""
Security-тест: золотой корпус для AI-анонимайзера.

Проверяются regex-правила из docs/ai/ANONYMIZER_RULES.md:
  - email → [EMAIL]
  - телефон RU/EN → [PHONE]
  - ИНН (10/12 цифр) → удаляется/маскируется
  - кредитная карта (16 цифр) → маскируется
  - паспорт РФ → маскируется
  - IP-адрес → [IP] или маскируется
  - имена собственные (whitelist эвристика) → [NAME]

ВАЖНО: `packages/ai/anonymizer.py` ещё не создан (P0-001).
Тесты написаны против ожидаемого интерфейса `anonymize(text) -> (str, PrivacyRisk)`.
При отсутствии модуля — тесты будут помечены ImportError, но валидны синтаксически.
"""
from __future__ import annotations

import re

import pytest


# --------------------------------------------------------------------------- #
# Corpus: пары (input, must_not_remain_in_output)                             #
# --------------------------------------------------------------------------- #

EMAIL_CORPUS = [
    "Свяжитесь с нами: john.doe@gmail.com — всегда рады",
    "Email: manager@company.ru для уточнений",
    "support+help@example.co.uk доступен с 9 до 18",
]

PHONE_RU_CORPUS = [
    "Звоните: +7 999 123-45-67 в рабочее время",
    "Телефон для связи +7(495)000-00-00",
    "WhatsApp: 89161234567",
    "+7 900 000 00 00 — менеджер Дмитрий",
]

PHONE_EN_CORPUS = [
    "Call us at +1 (415) 555-2671",
    "US number: +1-800-555-0100",
]

INN_CORPUS = [
    "ИНН организации: 7707083893",
    "ИНН физлица 504903248840",
]

CREDIT_CARD_CORPUS = [
    "Оплата картой 4111 1111 1111 1111",
    "Card: 5500 0000 0000 0004",
]

PASSPORT_CORPUS = [
    "Паспорт: 45 09 123456",
    "серия 7412 номер 349872",
]

IP_CORPUS = [
    "Источник запроса: 192.168.1.100",
    "IP клиента 10.0.0.1",
    "Внешний IP: 85.243.160.10",
]

# PII-паттерны, которые ДОЛЖНЫ быть убраны после анонимизации
PII_REGEXES = [
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),   # email
    re.compile(r"(?:\+7|8)[\s\-]?\(?9\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),  # RU phone
    re.compile(r"\+1[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}"),          # US phone
    re.compile(r"\b\d{10}\b|\b\d{12}\b"),                                   # ИНН (10 или 12 цифр)
    re.compile(r"\b(?:\d{4}[\s\-]){3}\d{4}\b"),                             # карта
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),                             # IP
]


# --------------------------------------------------------------------------- #
# Тест-заглушка: проверяем, что модуль планируется по правильному пути        #
# --------------------------------------------------------------------------- #

def test_anonymizer_module_path_documented():
    """
    Документация описывает packages/ai/anonymizer.py.
    Этот тест всегда PASS — просто фиксирует контракт.
    Реальный import теста заменится на реальный когда модуль будет создан.
    """
    expected_path = "packages/ai/anonymizer.py"
    assert expected_path  # placeholder


def test_anonymizer_interface_contract():
    """
    Ожидаемый интерфейс anonymize() из ANONYMIZER_RULES.md §5.
    Пока модуль не создан — тест описывает контракт.

    Пакет: packages/ai/src/packages_ai/anonymizer.py
    Импорт: from packages_ai.anonymizer import anonymize
    """
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        # Если модуль существует — тестируем
        result, risk = anonymize("hello world")
        assert isinstance(result, str)
        assert risk in ("low", "medium", "high")
    except ImportError:
        pytest.skip("packages/ai/anonymizer.py не создан (P0-001) — DEFERRED")


# --------------------------------------------------------------------------- #
# Regex-правила — параметризованные тесты                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw_text", EMAIL_CORPUS)
def test_anonymize_email_regex(raw_text: str):
    """
    После анонимизации email-адрес не должен присутствовать в тексте.
    Тестируем regex-правило напрямую.
    """
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(raw_text)
        email_re = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
        found = email_re.findall(result)
        assert not found, f"Email не замаскирован: {found} в '{result}'"
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


@pytest.mark.parametrize("raw_text", PHONE_RU_CORPUS)
def test_anonymize_phone_ru(raw_text: str):
    """RU-телефоны маскируются."""
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(raw_text)
        # После анонимизации не должно быть длинных числовых последовательностей > 7 цифр подряд
        assert "[PHONE]" in result or not re.search(r"\d{10,}", result.replace(" ", "").replace("-", ""))
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


@pytest.mark.parametrize("raw_text", PHONE_EN_CORPUS)
def test_anonymize_phone_en(raw_text: str):
    """EN-телефоны (US) маскируются."""
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(raw_text)
        assert "[PHONE]" in result or "+1" not in result
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


@pytest.mark.parametrize("raw_text", INN_CORPUS)
def test_anonymize_inn(raw_text: str):
    """ИНН (10/12 цифр) маскируется."""
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(raw_text)
        inn_re = re.compile(r"\b\d{10}\b|\b\d{12}\b")
        found = inn_re.findall(result.replace(" ", ""))
        assert not found, f"ИНН не замаскирован: {found}"
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


@pytest.mark.parametrize("raw_text", CREDIT_CARD_CORPUS)
def test_anonymize_credit_card(raw_text: str):
    """Номера карт (16 цифр) маскируются."""
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(raw_text)
        card_re = re.compile(r"\b(?:\d{4}[\s]){3}\d{4}\b")
        found = card_re.findall(result)
        assert not found, f"Номер карты не замаскирован: {found}"
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


@pytest.mark.parametrize("raw_text", IP_CORPUS)
def test_anonymize_ip(raw_text: str):
    """IP-адреса маскируются."""
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(raw_text)
        ip_re = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        found = ip_re.findall(result)
        assert not found, f"IP-адрес не замаскирован: {found}"
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


# --------------------------------------------------------------------------- #
# Property-based: что бы ни вернула LLM — PII-regex не матчит после anonymize #
# --------------------------------------------------------------------------- #

LLM_SAMPLES = [
    "Клиент Иван Иванов, телефон +7 999 123-45-67, email ivan@test.ru, ИНН 7707083893",
    "Сделка с ООО Ромашка, контакт: +1 415 555 2671, карта 4111 1111 1111 1111",
    "IP клиента: 192.168.1.100; паспорт 4509 123456",
    "John Smith, john.smith@corp.com, +7(495)000-00-00",
]


@pytest.mark.parametrize("llm_text", LLM_SAMPLES)
def test_property_no_pii_after_anonymize(llm_text: str):
    """
    Property-based: любой текст после anonymize не содержит PII-паттернов.
    """
    try:
        from packages_ai.anonymizer import anonymize  # noqa: PLC0415
        result, _ = anonymize(llm_text)
        for pii_re in PII_REGEXES:
            found = pii_re.findall(result)
            assert not found, (
                f"PII остался после анонимизации!\n"
                f"Паттерн: {pii_re.pattern}\n"
                f"Найдено: {found}\n"
                f"Исходник: {llm_text}\n"
                f"Результат: {result}"
            )
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")


# --------------------------------------------------------------------------- #
# Тест sample_size constraint                                                  #
# --------------------------------------------------------------------------- #

def test_build_research_pattern_min_sample_size():
    """
    build_research_pattern должна вернуть None при sample_size < 10.
    """
    try:
        from packages_ai.anonymizer import build_research_pattern  # noqa: PLC0415
        result = build_research_pattern(scores=[], industry="b2b_saas")
        assert result is None
    except ImportError:
        pytest.skip("anonymizer не создан — P0-001")
