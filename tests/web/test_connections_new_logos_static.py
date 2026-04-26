from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps/web/app/[locale]/app/connections/new/page.tsx"
PUBLIC = ROOT / "apps/web/public"
MESSAGES = [
    ROOT / "apps/web/messages/ru.json",
    ROOT / "apps/web/messages/en.json",
    ROOT / "apps/web/messages/es.json",
]


def test_connections_new_page_uses_crm_logo_assets() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'src="/amocrm-wordmark.png"' in source
    assert 'alt="amoCRM"' in source
    assert 'src="/kommo-wordmark.svg"' in source
    assert 'alt="Kommo"' in source
    assert 'src="/bitrix24-wordmark.svg"' in source
    assert 'alt="Bitrix24"' in source
    assert 'src="/email-wordmark.svg"' in source
    assert "function IntegrationLogo" in source
    assert "h-36 w-full" in source
    assert "md:h-40" in source
    assert "max-h-28" in source
    assert "items-center text-center" in source
    assert "object-center" in source

    assert (PUBLIC / "amocrm-wordmark.png").is_file()
    assert (PUBLIC / "kommo-wordmark.svg").is_file()
    assert (PUBLIC / "bitrix24-wordmark.svg").is_file()
    assert (PUBLIC / "email-wordmark.svg").is_file()
    email_logo = (PUBLIC / "email-wordmark.svg").read_text(encoding="utf-8")
    assert "email-circle-gradient" in email_logo
    assert "<circle" in email_logo


def test_connections_new_page_keeps_amocrm_external_button_flow() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "AmoCrmExternalButton" in source
    assert "/integrations/amocrm/oauth/start" in source
    assert "/integrations/amocrm/oauth/button-config" in source
    assert "external_button" in source


def test_connections_new_page_hides_external_button_technical_details() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "externalButtonModeTitle" not in source
    assert "externalButtonModeDesc" not in source
    assert "externalButtonWebhookLabel" not in source
    assert "buttonConfig?.secrets_uri" not in source
    assert "buttonConfig?.webhook_url" not in source


def test_connections_new_page_does_not_show_mock_crm_action() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "connectMock" not in source
    assert "/crm/connections/mock-amocrm" not in source
    assert "amoCRM (mock)" not in source


def test_connection_messages_do_not_expose_mock_amocrm_cta() -> None:
    for path in MESSAGES:
        messages = path.read_text(encoding="utf-8")
        assert "connectMock" not in messages
        assert "mockNote" not in messages
        assert "amoCRM (mock)" not in messages
