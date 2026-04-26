"""
ORM-модели main-schema.

**Совместная зона BE + DW** (см. `docs/architecture/FILE_OWNERSHIP.md`).
Любое изменение полей/индексов требует согласования с DW — он пишет миграции.

Имена и поля синхронизированы с `docs/db/SCHEMA.md`.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import relationship

from app.db.models._helpers import INET, JSONB, UUID, enum_check, now_default, uuid_pk
from app.db.models.base import MainBase
from app.db.models.enums import (
    AdminRole,
    AdminUserStatus,
    AiAnalysisJobKind,
    AiAnalysisJobStatus,
    AiFrequencyBucket,
    AiKnowledgeSource,
    AiKnowledgeStatus,
    AiModelProvider,
    AiModelRunStatus,
    AiResearchConsentStatus,
    BillingCurrency,
    BillingLedgerKind,
    BillingPlan,
    BillingProvider,
    CrmConnectionStatus,
    CrmProvider,
    DeletionRequestStatus,
    EmailVerificationPurpose,
    JobKind,
    JobQueue,
    JobStatus,
    Locale,
    NotificationKind,
    TokenAccountPlan,
    TokenLedgerKind,
    TokenReservationStatus,
    UserStatus,
    WorkspaceMemberRole,
    WorkspaceStatus,
)


# ---------- 1.1 users ----------
class User(MainBase):
    __tablename__ = "users"

    id = uuid_pk()
    email = Column(CITEXT(), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    display_name = Column(Text, nullable=True)
    locale = Column(Text, nullable=False, server_default="ru")
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    two_factor_enabled = Column(Boolean, nullable=False, server_default="false")
    two_factor_secret_encrypted = Column(LargeBinary, nullable=True)
    status = Column(Text, nullable=False, server_default="active")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("status", UserStatus, "ck_users_status"),
        enum_check("locale", Locale, "ck_users_locale"),
        Index("ix_users_status", "status"),
    )


# ---------- 1.2 user_sessions ----------
class UserSession(MainBase):
    __tablename__ = "user_sessions"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refresh_token_hash = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)
    ip = Column(INET(), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_user_sessions_user_active", "user_id", "revoked_at"),
        Index("ix_user_sessions_expires", "expires_at"),
    )


# ---------- 1.3 email_verification_codes ----------
class EmailVerificationCode(MainBase):
    __tablename__ = "email_verification_codes"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose = Column(Text, nullable=False)
    code_hash = Column(Text, nullable=False)
    attempts = Column(Integer, nullable=False, server_default="0")
    max_attempts = Column(Integer, nullable=False, server_default="5")
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("purpose", EmailVerificationPurpose, "ck_evc_purpose"),
        Index("ix_evc_user_purpose", "user_id", "purpose"),
        Index("ix_evc_expires", "expires_at"),
    )


# ---------- 1.4 workspaces ----------
class Workspace(MainBase):
    __tablename__ = "workspaces"

    id = uuid_pk()
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    locale = Column(Text, nullable=False, server_default="ru")
    industry = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        enum_check("status", WorkspaceStatus, "ck_workspace_status"),
        enum_check("locale", Locale, "ck_workspace_locale"),
        Index("ix_workspaces_owner", "owner_user_id"),
        Index("ix_workspaces_status", "status"),
    )


# ---------- 1.5 workspace_members ----------
class WorkspaceMember(MainBase):
    __tablename__ = "workspace_members"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("role", WorkspaceMemberRole, "ck_wsmember_role"),
        UniqueConstraint("workspace_id", "user_id", name="uq_wsmember_ws_user"),
        Index("ix_wsmember_user", "user_id"),
    )


# ---------- 1.6 crm_connections ----------
class CrmConnection(MainBase):
    __tablename__ = "crm_connections"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name = Column(Text, nullable=True)  # удобное имя для пользователя
    provider = Column(Text, nullable=False)
    external_account_id = Column(Text, nullable=True)
    external_domain = Column(Text, nullable=True)
    tenant_schema = Column(Text, nullable=True, unique=True)
    status = Column(Text, nullable=False, server_default="pending")
    access_token_encrypted = Column(LargeBinary, nullable=True)
    refresh_token_encrypted = Column(LargeBinary, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")

    # --- amoCRM external_button (#44.6) ---
    # Режим получения client_id/secret:
    #   static_client — общий для всех (settings.amocrm_client_id);
    #   external_button — пришёл от amoCRM вебхуком, хранится per-connection.
    # Для static_client поля amocrm_* остаются NULL.
    amocrm_auth_mode = Column(Text, nullable=True)
    # Per-installation OAuth-credentials (external_button).
    amocrm_client_id = Column(Text, nullable=True)
    amocrm_client_secret_encrypted = Column(LargeBinary, nullable=True)
    # ID интеграции, который amoCRM создала у клиента (для последующего uninstall).
    amocrm_external_integration_id = Column(Text, nullable=True)
    # Когда именно webhook доставил credentials — нужно для race-debug'а callback'а.
    amocrm_credentials_received_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        enum_check("provider", CrmProvider, "ck_crmconn_provider"),
        enum_check("status", CrmConnectionStatus, "ck_crmconn_status"),
        Index("ix_crmconn_workspace", "workspace_id"),
        Index("ix_crmconn_status", "status"),
        Index(
            "ix_crmconn_amo_integration",
            "amocrm_external_integration_id",
            postgresql_where=text("amocrm_external_integration_id IS NOT NULL"),
        ),
    )


# ---------- 1.6b dashboard builder ----------
class Dashboard(MainBase):
    __tablename__ = "dashboards"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(Text, nullable=False, server_default="Основной дашборд")
    status = Column(Text, nullable=False, server_default="active")
    filters = Column(JSONB, nullable=False, server_default="{}")
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_dash_status"),
        UniqueConstraint("crm_connection_id", "name", name="uq_dash_conn_name"),
        Index("ix_dash_ws", "workspace_id"),
        Index("ix_dash_conn", "crm_connection_id"),
    )


class DashboardWidget(MainBase):
    __tablename__ = "dashboard_widgets"

    id = uuid_pk()
    dashboard_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    widget_key = Column(Text, nullable=False)
    widget_type = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    x = Column(Integer, nullable=False, server_default="0")
    y = Column(Integer, nullable=False, server_default="0")
    w = Column(Integer, nullable=False, server_default="4")
    h = Column(Integer, nullable=False, server_default="3")
    config = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        UniqueConstraint("dashboard_id", "widget_key", name="uq_dash_widget_key"),
        CheckConstraint("w >= 2 AND w <= 12", name="ck_dash_widget_w"),
        CheckConstraint("h >= 2 AND h <= 12", name="ck_dash_widget_h"),
        Index("ix_dash_widget_dash", "dashboard_id"),
    )


class DashboardShare(MainBase):
    __tablename__ = "dashboard_shares"

    id = uuid_pk()
    dashboard_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, server_default="active")
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_dashshare_status"),
        Index("ix_dashshare_dash_status", "dashboard_id", "status"),
    )


# ---------- 1.6c universal analytics catalog ----------
class CrmFieldMapping(MainBase):
    __tablename__ = "crm_field_mappings"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider = Column(Text, nullable=False, server_default="amocrm")
    entity_type = Column(Text, nullable=False)
    metric_key = Column(Text, nullable=False)
    field_id = Column(Text, nullable=True)
    field_name = Column(Text, nullable=True)
    field_type = Column(Text, nullable=True)
    value_type = Column(Text, nullable=False, server_default="string")
    status = Column(Text, nullable=False, server_default="active")
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('deal','contact','company','task','note','call','message')",
            name="ck_crmfieldmap_entity",
        ),
        CheckConstraint(
            "status IN ('active','disabled','missing')",
            name="ck_crmfieldmap_status",
        ),
        UniqueConstraint("crm_connection_id", "metric_key", name="uq_crmfieldmap_conn_metric"),
        Index("ix_crmfieldmap_workspace", "workspace_id"),
        Index("ix_crmfieldmap_connection", "crm_connection_id"),
    )


class DashboardTemplate(MainBase):
    __tablename__ = "dashboard_templates"

    id = uuid_pk()
    template_key = Column(Text, nullable=False, unique=True)
    title = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    pages = Column(JSONB, nullable=False, server_default="[]")
    widgets = Column(JSONB, nullable=False, server_default="[]")
    requirements = Column(JSONB, nullable=False, server_default="[]")
    status = Column(Text, nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="ck_dashtpl_status"),
        Index("ix_dashtpl_category", "category"),
        Index("ix_dashtpl_status", "status"),
    )


class AiTenantInsight(MainBase):
    __tablename__ = "ai_tenant_insights"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    analysis_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_kind = Column(Text, nullable=False)
    source_ref = Column(JSONB, nullable=False, server_default="{}")
    insight_type = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=True)
    score = Column(Numeric(5, 2), nullable=True)
    payload = Column(JSONB, nullable=False, server_default="{}")
    status = Column(Text, nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('deal','call','message','email','chat','manager','pipeline')",
            name="ck_aitenant_source_kind",
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_aitenant_status"),
        Index("ix_aitenant_workspace_created", "workspace_id", "created_at"),
        Index("ix_aitenant_conn_type", "crm_connection_id", "insight_type"),
        Index("ix_aitenant_job", "analysis_job_id"),
    )


# ---------- 1.7 billing_accounts ----------
class BillingAccount(MainBase):
    __tablename__ = "billing_accounts"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id"),
        nullable=False,
        unique=True,
    )
    currency = Column(Text, nullable=False, server_default="RUB")
    balance_cents = Column(BigInteger, nullable=False, server_default="0")
    plan = Column(Text, nullable=False, server_default="free")
    provider = Column(Text, nullable=False, server_default="yookassa")
    external_customer_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("currency", BillingCurrency, "ck_billacc_currency"),
        enum_check("plan", BillingPlan, "ck_billacc_plan"),
        enum_check("provider", BillingProvider, "ck_billacc_provider"),
    )


# ---------- 1.8 billing_ledger ----------
class BillingLedger(MainBase):
    __tablename__ = "billing_ledger"

    id = uuid_pk()
    billing_account_id = Column(
        UUID(as_uuid=True), ForeignKey("billing_accounts.id"), nullable=False
    )
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    currency = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    reference = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("kind", BillingLedgerKind, "ck_billledger_kind"),
        Index("ix_billledger_account_created", "billing_account_id", "created_at"),
        Index("ix_billledger_workspace", "workspace_id"),
    )


# ---------- 1.8a payment_orders ----------
class PaymentOrder(MainBase):
    __tablename__ = "payment_orders"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider = Column(Text, nullable=False, server_default="tbank")
    method = Column(Text, nullable=False)
    purpose = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    amount_cents = Column(BigInteger, nullable=False)
    currency = Column(Text, nullable=False, server_default="RUB")
    token_amount_mtokens = Column(BigInteger, nullable=False, server_default="0")
    plan_key = Column(Text, nullable=True)
    period_months = Column(Integer, nullable=True)
    external_order_id = Column(Text, nullable=False, unique=True)
    external_payment_id = Column(Text, nullable=True)
    payment_url = Column(Text, nullable=True)
    invoice_number = Column(Text, nullable=True)
    payer_inn = Column(Text, nullable=True)
    payer_kpp = Column(Text, nullable=True)
    payer_name = Column(Text, nullable=True)
    payer_ogrn = Column(Text, nullable=True)
    payer_address = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    paid_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("method IN ('card','invoice')", name="ck_payorder_method"),
        CheckConstraint("purpose IN ('token_topup','subscription')", name="ck_payorder_purpose"),
        CheckConstraint(
            "status IN ('pending','paid','failed','cancelled','manual_review')",
            name="ck_payorder_status",
        ),
        CheckConstraint("amount_cents > 0", name="ck_payorder_amount_positive"),
        CheckConstraint("token_amount_mtokens >= 0", name="ck_payorder_tokens_nonnegative"),
        Index("ix_payorder_workspace_created", "workspace_id", "created_at"),
        Index("ix_payorder_status_created", "status", "created_at"),
        Index("ix_payorder_external_payment", "external_payment_id"),
    )


# ---------- 1.8b token_accounts ----------
class TokenAccount(MainBase):
    __tablename__ = "token_accounts"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan_key = Column(Text, nullable=False, server_default="free")
    included_monthly_mtokens = Column(BigInteger, nullable=False, server_default="0")
    balance_mtokens = Column(BigInteger, nullable=False, server_default="0")
    reserved_mtokens = Column(BigInteger, nullable=False, server_default="0")
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("plan_key", TokenAccountPlan, "ck_tokenacc_plan_key"),
        CheckConstraint("included_monthly_mtokens >= 0", name="ck_tokenacc_included_nonnegative"),
        CheckConstraint("balance_mtokens >= 0", name="ck_tokenacc_balance_nonnegative"),
        CheckConstraint("reserved_mtokens >= 0", name="ck_tokenacc_reserved_nonnegative"),
        CheckConstraint("reserved_mtokens <= balance_mtokens", name="ck_tokenacc_reserved_lte_balance"),
        Index("ix_tokenacc_workspace", "workspace_id"),
    )


# ---------- 1.8c token_reservations ----------
class TokenReservation(MainBase):
    __tablename__ = "token_reservations"

    id = uuid_pk()
    token_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("token_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    amount_mtokens = Column(BigInteger, nullable=False)
    status = Column(Text, nullable=False, server_default="reserved")
    reason = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    finalized_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        enum_check("status", TokenReservationStatus, "ck_tokenres_status"),
        CheckConstraint("amount_mtokens > 0", name="ck_tokenres_amount_positive"),
        UniqueConstraint("job_id", name="uq_tokenres_job"),
        Index("ix_tokenres_workspace_created", "workspace_id", "created_at"),
        Index("ix_tokenres_status_created", "status", "created_at"),
        Index("ix_tokenres_connection", "crm_connection_id"),
    )


# ---------- 1.8d token_ledger ----------
class TokenLedger(MainBase):
    __tablename__ = "token_ledger"

    id = uuid_pk()
    token_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("token_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    reservation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("token_reservations.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount_mtokens = Column(BigInteger, nullable=False)
    balance_after_mtokens = Column(BigInteger, nullable=False)
    reserved_after_mtokens = Column(BigInteger, nullable=False)
    kind = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    reference = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("kind", TokenLedgerKind, "ck_tokenledger_kind"),
        Index("ix_tokenledger_account_created", "token_account_id", "created_at"),
        Index("ix_tokenledger_workspace_created", "workspace_id", "created_at"),
        Index("ix_tokenledger_connection", "crm_connection_id"),
        Index("ix_tokenledger_job", "job_id"),
    )


# ---------- 1.9 jobs ----------
class Job(MainBase):
    __tablename__ = "jobs"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind = Column(Text, nullable=False)
    queue = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="queued")
    payload = Column(JSONB, nullable=False, server_default="{}")
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    rq_job_id = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("kind", JobKind, "ck_job_kind"),
        enum_check("queue", JobQueue, "ck_job_queue"),
        enum_check("status", JobStatus, "ck_job_status"),
        Index("ix_jobs_workspace_created", "workspace_id", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_rq_id", "rq_job_id"),
    )


# ---------- 1.10 notifications ----------
class Notification(MainBase):
    __tablename__ = "notifications"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    kind = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("kind", NotificationKind, "ck_notif_kind"),
        Index("ix_notif_workspace_read", "workspace_id", "read_at", "created_at"),
    )


# ---------- 1.11 admin_users ----------
class AdminUser(MainBase):
    __tablename__ = "admin_users"

    id = uuid_pk()
    email = Column(CITEXT(), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    display_name = Column(Text, nullable=True)
    role = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="active")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("role", AdminRole, "ck_adminuser_role"),
        enum_check("status", AdminUserStatus, "ck_adminuser_status"),
    )


# ---------- 1.12 admin_audit_logs ----------
class AdminAuditLog(MainBase):
    __tablename__ = "admin_audit_logs"

    id = uuid_pk()
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=False)
    action = Column(Text, nullable=False)
    target_type = Column(Text, nullable=True)
    target_id = Column(UUID(as_uuid=True), nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    ip = Column(INET(), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_adminaudit_admin_created", "admin_user_id", "created_at"),
        Index("ix_adminaudit_action", "action"),
        Index("ix_adminaudit_target", "target_type", "target_id"),
    )


# ---------- 1.13 deletion_requests ----------
class DeletionRequest(MainBase):
    __tablename__ = "deletion_requests"

    id = uuid_pk()
    crm_connection_id = Column(
        UUID(as_uuid=True), ForeignKey("crm_connections.id"), nullable=False
    )
    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(Text, nullable=False, server_default="awaiting_code")
    email_code_hash = Column(Text, nullable=False)
    attempts = Column(Integer, nullable=False, server_default="0")
    max_attempts = Column(Integer, nullable=False, server_default="5")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("status", DeletionRequestStatus, "ck_delreq_status"),
        Index("ix_delreq_conn_status", "crm_connection_id", "status"),
        Index("ix_delreq_expires", "expires_at"),
    )


# ---------- 1.14.1 ai_analysis_jobs ----------
class AiAnalysisJob(MainBase):
    __tablename__ = "ai_analysis_jobs"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    crm_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind = Column(Text, nullable=False)
    input_ref = Column(JSONB, nullable=False)
    prompt_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_prompt_versions.id"),
        nullable=True,
    )
    model_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_model_runs.id"),
        nullable=True,
    )
    status = Column(Text, nullable=False, server_default="queued")
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("kind", AiAnalysisJobKind, "ck_aiaj_kind"),
        enum_check("status", AiAnalysisJobStatus, "ck_aiaj_status"),
        Index("ix_aiaj_workspace_created", "workspace_id", "created_at"),
        Index("ix_aiaj_status", "status"),
    )


# ---------- 1.14.2 ai_conversation_scores ----------
class AiConversationScore(MainBase):
    __tablename__ = "ai_conversation_scores"

    id = uuid_pk()
    analysis_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    overall_score = Column(Numeric(5, 2), nullable=True)
    dimension_scores = Column(JSONB, nullable=False, server_default="{}")
    strengths = Column(JSONB, nullable=False, server_default="[]")
    weaknesses = Column(JSONB, nullable=False, server_default="[]")
    recommendations = Column(JSONB, nullable=False, server_default="[]")
    confidence = Column(Numeric(3, 2), nullable=True)
    raw_llm_output = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_aics_workspace_created", "workspace_id", "created_at"),
        Index("ix_aics_job", "analysis_job_id"),
    )


# ---------- 1.14.3 ai_behavior_patterns ----------
class AiBehaviorPattern(MainBase):
    __tablename__ = "ai_behavior_patterns"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    pattern_type = Column(Text, nullable=False)
    frequency_bucket = Column(Text, nullable=False)
    sample_size = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    evidence_refs = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("frequency_bucket", AiFrequencyBucket, "ck_aibp_freq"),
        CheckConstraint("sample_size >= 10", name="ck_aibp_sample_size"),
        Index("ix_aibp_ws_type", "workspace_id", "pattern_type"),
    )


# ---------- 1.14.4 ai_client_knowledge_items ----------
class AiClientKnowledgeItem(MainBase):
    __tablename__ = "ai_client_knowledge_items"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    source = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_prompt_versions.id"),
        nullable=True,
    )
    status = Column(Text, nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("source", AiKnowledgeSource, "ck_aikb_source"),
        enum_check("status", AiKnowledgeStatus, "ck_aikb_status"),
        Index("ix_aikb_ws_status", "workspace_id", "status"),
    )


# ---------- 1.14.5 ai_research_consent ----------
class AiResearchConsent(MainBase):
    __tablename__ = "ai_research_consent"

    id = uuid_pk()
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status = Column(Text, nullable=False, server_default="not_asked")
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    terms_version = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("status", AiResearchConsentStatus, "ck_airc_status"),
    )


# ---------- 1.14.6 ai_research_patterns ----------
class AiResearchPattern(MainBase):
    """
    Полностью анонимизированный агрегат паттернов по индустрии.

    БЕЗ FK на workspace/user — только статистика по consent-положительным
    workspaces. ``sample_size >= 10`` — статистическое требование анонимности.
    """

    __tablename__ = "ai_research_patterns"

    id = uuid_pk()
    industry = Column(Text, nullable=True)
    pattern_type = Column(Text, nullable=False)
    channel = Column(Text, nullable=True)
    objection_type = Column(Text, nullable=True)
    response_type = Column(Text, nullable=True)
    duration_bucket = Column(Text, nullable=True)
    period_bucket = Column(Text, nullable=True)
    sample_size = Column(Integer, nullable=False)
    confidence = Column(Numeric(3, 2), nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint("sample_size >= 10", name="ck_airp_sample_size"),
        Index("ix_airp_industry_type", "industry", "pattern_type"),
        Index("ix_airp_period", "period_bucket"),
    )


# ---------- 1.14.7 ai_prompt_versions ----------
class AiPromptVersion(MainBase):
    __tablename__ = "ai_prompt_versions"

    id = uuid_pk()
    key = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    template = Column(Text, nullable=False)
    params = Column(JSONB, nullable=False, server_default="{}")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_aipv_key_ver"),
        Index("ix_aipv_key_active", "key", "is_active"),
    )


# ---------- 1.14.8 ai_model_runs ----------
class AiModelRun(MainBase):
    __tablename__ = "ai_model_runs"

    id = uuid_pk()
    provider = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    prompt_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_prompt_versions.id"),
        nullable=True,
    )
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    cost_cents = Column(Integer, nullable=True)
    status = Column(Text, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("provider", AiModelProvider, "ck_aimr_provider"),
        enum_check("status", AiModelRunStatus, "ck_aimr_status"),
        Index("ix_aimr_provider_model_created", "provider", "model", "created_at"),
    )


# ---------- Admin sessions & Support sessions (Wave 2 доп.) ----------
class AdminSession(MainBase):
    """Refresh-сессии для админов (аналог user_sessions)."""

    __tablename__ = "admin_sessions"

    id = uuid_pk()
    admin_user_id = Column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_token_hash = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)
    ip = Column(INET(), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_admsess_admin_revoked", "admin_user_id", "revoked_at"),
        Index("ix_admsess_expires", "expires_at"),
    )


class AdminSupportSession(MainBase):
    """Сессии support-mode для чтения tenant-данных (TTL 60 минут)."""

    __tablename__ = "admin_support_sessions"

    id = uuid_pk()
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=False)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_sup_admin_created", "admin_user_id", "created_at"),
        Index("ix_sup_ws", "workspace_id"),
        Index("ix_sup_active", "ended_at", "expires_at"),
    )


# Re-export базовых классов + tenant-модели, чтобы Backend и worker
# импортировали всё из ``app.db.models``.
from app.db.models.base import MainBase, TenantBase  # noqa: E402, F401
from app.db.models.tenant_schema import (  # noqa: E402, F401
    Call,
    Chat,
    Company,
    Contact,
    CrmUser,
    Deal,
    DealProduct,
    DealTag,
    KnowledgeBaseVersion,
    Message,
    Note,
    Pipeline,
    Product,
    RawCall,
    RawChat,
    RawCompany,
    RawContact,
    RawDeal,
    RawEvent,
    RawMessage,
    RawNote,
    RawPipeline,
    RawProduct,
    RawStage,
    RawTag,
    RawTask,
    RawUser,
    Stage,
    Tag,
    Task,
)

__all__ = [
    # Bases
    "MainBase",
    "TenantBase",
    # Main-schema entities
    "User",
    "UserSession",
    "EmailVerificationCode",
    "Workspace",
    "WorkspaceMember",
    "CrmConnection",
    "Dashboard",
    "DashboardWidget",
    "DashboardShare",
    "BillingAccount",
    "BillingLedger",
    "PaymentOrder",
    "TokenAccount",
    "TokenLedger",
    "TokenReservation",
    "Job",
    "Notification",
    "AdminUser",
    "AdminAuditLog",
    "AdminSession",
    "AdminSupportSession",
    "DeletionRequest",
    "AiAnalysisJob",
    "AiConversationScore",
    "AiBehaviorPattern",
    "AiClientKnowledgeItem",
    "AiResearchConsent",
    "AiResearchPattern",
    "AiPromptVersion",
    "AiModelRun",
    # Tenant-schema entities
    "RawDeal",
    "RawContact",
    "RawCompany",
    "RawTask",
    "RawNote",
    "RawEvent",
    "RawCall",
    "RawChat",
    "RawMessage",
    "RawUser",
    "RawPipeline",
    "RawStage",
    "RawProduct",
    "RawTag",
    "Deal",
    "Contact",
    "Company",
    "Task",
    "Note",
    "Call",
    "Chat",
    "Message",
    "Pipeline",
    "Stage",
    "CrmUser",
    "Product",
    "Tag",
    "DealTag",
    "DealProduct",
    "KnowledgeBaseVersion",
]
