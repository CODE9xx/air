"""
Настройки приложения через pydantic-settings.

Все переменные — из окружения (см. `.env.example` в корне репозитория).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Общие
    app_env: str = Field(default="development", alias="APP_ENV")
    base_url: str = Field(default="http://localhost:8000", alias="BASE_URL")
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://code9:code9@localhost:5432/code9",
        alias="DATABASE_URL",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # JWT
    jwt_secret: str = Field(default="dev-jwt-secret-change-me", alias="JWT_SECRET")
    admin_jwt_secret: str = Field(
        default="dev-admin-jwt-secret-change-me", alias="ADMIN_JWT_SECRET"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_ttl_seconds: int = Field(default=900, alias="ACCESS_TOKEN_TTL_SECONDS")
    refresh_token_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 30, alias="REFRESH_TOKEN_TTL_SECONDS"
    )

    # Fernet (для OAuth-токенов и 2FA секрета)
    fernet_key: str = Field(
        default="V2fZ7eYm_Qc_f0p-Jb5HcH8XxJz0Aq7W1GH8wKmYP_M=", alias="FERNET_KEY"
    )

    # CRM
    mock_crm_mode: bool = Field(default=True, alias="MOCK_CRM_MODE")

    # amoCRM OAuth (используется только при MOCK_CRM_MODE=false)
    #
    # AMOCRM_AUTH_MODE:
    #   * static_client (default) — одна "общая" интеграция в amoCRM;
    #     все клиенты делят один CLIENT_ID/CLIENT_SECRET. Классический путь
    #     из mini-apps.
    #   * external_button — amoCRM создаёт интеграцию в момент нажатия
    #     кнопки "Установить" на стороне клиента, присылает CLIENT_ID/
    #     CLIENT_SECRET вебхуком на AMOCRM_EXTERNAL_WEBHOOK_URL, и уже
    #     после этого начинается стандартный OAuth. Credentials храним
    #     ПО-УСТАНОВЛИВАЮЩЕ, Fernet-шифрованный secret в БД.
    #
    # Оба режима требуют AMOCRM_REDIRECT_URI (совпадающий с панелью amoCRM).
    amocrm_auth_mode: str = Field(default="static_client", alias="AMOCRM_AUTH_MODE")
    amocrm_client_id: str = Field(default="", alias="AMOCRM_CLIENT_ID")
    amocrm_client_secret: str = Field(default="", alias="AMOCRM_CLIENT_SECRET")
    amocrm_redirect_uri: str = Field(default="", alias="AMOCRM_REDIRECT_URI")
    # AMOCRM_SECRETS_URI — публичный HTTPS-endpoint, на который amoCRM присылает
    # client_id / client_secret при external_button режиме (official amoCRM
    # External Integration Button terminology: data-secrets_uri).
    # Обычно: `${BASE_URL}/api/v1/integrations/amocrm/external/secrets`.
    # AMOCRM_EXTERNAL_WEBHOOK_URL — deprecated legacy-alias; если задан и
    # AMOCRM_SECRETS_URI пуст, используется как fallback (см. свойство
    # `effective_amocrm_secrets_uri`). Оба хранятся, чтобы старые
    # `.env.production` не ломались на выкатке.
    amocrm_secrets_uri: str = Field(default="", alias="AMOCRM_SECRETS_URI")
    amocrm_external_webhook_url: str = Field(
        default="", alias="AMOCRM_EXTERNAL_WEBHOOK_URL"
    )
    # Сколько секунд callback ждёт прихода credentials от webhook при
    # external_button (amoCRM может прислать webhook с небольшой задержкой
    # относительно user-агента). 5с/0.5с backoff — подобрано эмпирически.
    amocrm_external_wait_seconds: float = Field(
        default=5.0, alias="AMOCRM_EXTERNAL_WAIT_SECONDS"
    )
    # amoCRM External Integration Button — публичная метаинформация, которая
    # идёт во фронтовый <script class="amocrm_oauth"> в data-* атрибутах.
    # Секретов не содержит; используется только для UX.
    amocrm_button_name: str = Field(default="", alias="AMOCRM_BUTTON_NAME")
    amocrm_button_description: str = Field(
        default="", alias="AMOCRM_BUTTON_DESCRIPTION"
    )
    amocrm_button_logo: str = Field(default="", alias="AMOCRM_BUTTON_LOGO")
    amocrm_button_scopes: str = Field(default="", alias="AMOCRM_BUTTON_SCOPES")
    amocrm_button_title: str = Field(default="", alias="AMOCRM_BUTTON_TITLE")

    # Email
    dev_email_mode: str = Field(default="log", alias="DEV_EMAIL_MODE")
    # console — в stdout/логи (dev).
    # smtp    — реальная отправка (prod, Timeweb SMTP и пр.).
    email_backend: str = Field(default="console", alias="EMAIL_BACKEND")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="noreply@example.com", alias="SMTP_FROM")
    # starttls (587) | ssl (465) | none (25, только dev/internal).
    smtp_mode: str = Field(default="starttls", alias="SMTP_MODE")
    smtp_timeout_seconds: int = Field(default=10, alias="SMTP_TIMEOUT_SECONDS")

    # Admin bootstrap
    admin_bootstrap_email: str = Field(
        default="admin@code9.local", alias="ADMIN_BOOTSTRAP_EMAIL"
    )
    admin_bootstrap_password: str = Field(
        default="change-me-on-first-login", alias="ADMIN_BOOTSTRAP_PASSWORD"
    )

    # Cookie
    refresh_cookie_name: str = Field(default="code9_refresh", alias="REFRESH_COOKIE_NAME")
    admin_refresh_cookie_name: str = Field(
        default="code9_admin_refresh", alias="ADMIN_REFRESH_COOKIE_NAME"
    )

    @model_validator(mode="after")
    def check_prod_secrets(self) -> "Settings":
        """
        Fail-fast проверка: если APP_ENV=production и секреты равны дефолтным
        публичным значениям — контейнер не стартует.

        CR-03 (QA, 2026-04-18): security-critical, закрыто Lead Architect.
        """
        if self.app_env in ("production", "prod"):
            _public_defaults: dict[str, str] = {
                "jwt_secret": "dev-jwt-secret-change-me",
                "admin_jwt_secret": "dev-admin-jwt-secret-change-me",
                "fernet_key": "V2fZ7eYm_Qc_f0p-Jb5HcH8XxJz0Aq7W1GH8wKmYP_M=",
            }
            for field_name, default_val in _public_defaults.items():
                if getattr(self, field_name) == default_val:
                    raise ValueError(
                        f"{field_name.upper()} не переопределён — "
                        "запуск в production с публичным дефолтом запрещён."
                    )

            # Если email_backend=smtp, требуем хотя бы host+from. Пароль может
            # отсутствовать у internal relay, но на Timeweb всегда есть.
            if self.email_backend.lower() == "smtp":
                if not self.smtp_host:
                    raise ValueError(
                        "EMAIL_BACKEND=smtp, но SMTP_HOST пустой — "
                        "письма отправлять невозможно."
                    )
                if not self.smtp_from or "@" not in self.smtp_from:
                    raise ValueError(
                        "SMTP_FROM должен быть валидным e-mail "
                        "(например, noreply@aicode9.ru)."
                    )

            # Real-CRM mode (MOCK_CRM_MODE=false) в проде требует набор
            # amoCRM-настроек; состав зависит от AMOCRM_AUTH_MODE:
            #
            # static_client  → CLIENT_ID + CLIENT_SECRET + REDIRECT_URI
            # external_button → AMOCRM_SECRETS_URI (или legacy
            #                   AMOCRM_EXTERNAL_WEBHOOK_URL) + REDIRECT_URI
            #                   (CLIENT_ID/SECRET приходят вебхуком per install)
            if not self.mock_crm_mode:
                _mode = (self.amocrm_auth_mode or "").lower().strip()
                if _mode not in {"static_client", "external_button"}:
                    raise ValueError(
                        f"AMOCRM_AUTH_MODE='{self.amocrm_auth_mode}' — "
                        "допустимы только 'static_client' или 'external_button'."
                    )

                if _mode == "static_client":
                    _amo_required = {
                        "AMOCRM_CLIENT_ID": self.amocrm_client_id,
                        "AMOCRM_CLIENT_SECRET": self.amocrm_client_secret,
                        "AMOCRM_REDIRECT_URI": self.amocrm_redirect_uri,
                    }
                else:  # external_button
                    # Принимаем primary AMOCRM_SECRETS_URI, либо legacy
                    # AMOCRM_EXTERNAL_WEBHOOK_URL как backward-compat fallback.
                    _effective_secrets_uri = self.effective_amocrm_secrets_uri
                    _amo_required = {
                        "AMOCRM_SECRETS_URI": _effective_secrets_uri,
                        "AMOCRM_REDIRECT_URI": self.amocrm_redirect_uri,
                    }
                _missing = [k for k, v in _amo_required.items() if not v]
                if _missing:
                    raise ValueError(
                        f"MOCK_CRM_MODE=false и AMOCRM_AUTH_MODE={_mode}, "
                        "но не заполнены: " + ", ".join(_missing) + ". "
                        "Заполни .env.production перед перезапуском либо "
                        "временно выставь MOCK_CRM_MODE=true."
                    )
                if not self.amocrm_redirect_uri.startswith("https://"):
                    raise ValueError(
                        "AMOCRM_REDIRECT_URI должен начинаться с https:// "
                        "(amoCRM не принимает http в prod)."
                    )
                if (
                    _mode == "external_button"
                    and not self.effective_amocrm_secrets_uri.startswith("https://")
                ):
                    raise ValueError(
                        "AMOCRM_SECRETS_URI должен быть публичным "
                        "https://-endpoint'ом — amoCRM не отдаёт credentials "
                        "на http. (Legacy alias AMOCRM_EXTERNAL_WEBHOOK_URL "
                        "тоже должен быть https, если используется.)"
                    )
        return self

    @property
    def effective_amocrm_secrets_uri(self) -> str:
        """
        Резолвит фактический secrets URI для external_button режима.

        Приоритет (совпадает с v2-спецификацией #44.6):
          1. `AMOCRM_SECRETS_URI` (primary, новое имя).
          2. `AMOCRM_EXTERNAL_WEBHOOK_URL` (legacy alias, backward compat).
          3. "" — вызывающий код решает, 501 это или 400.

        Никаких секретов не содержит — вся строка попадает во фронтовый
        data-secrets_uri и в /button-config JSON.
        """
        if self.amocrm_secrets_uri:
            return self.amocrm_secrets_uri
        if self.amocrm_external_webhook_url:
            return self.amocrm_external_webhook_url
        return ""

    @property
    def allowed_origins_list(self) -> list[str]:
        """CORS — список разрешённых origin'ов."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """В prod — cookie ставим secure=True."""
        return self.app_env in {"production", "prod"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный синглтон настроек."""
    return Settings()
