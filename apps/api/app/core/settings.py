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
        return self

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
