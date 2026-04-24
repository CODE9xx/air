"""
Все строковые enum'ы из ``docs/db/SCHEMA.md`` — в одном месте.

Для ORM используем Python ``StrEnum``, для Postgres мапим через ``text+CHECK``
(Alembic-миграция создаёт ``CHECK`` constraint). Это даёт гибкость: добавить
новое значение можно обычной миграцией, без ``ALTER TYPE``.
"""
from __future__ import annotations

from enum import StrEnum


# ---------- Main schema ----------

class UserStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"
    DELETED = "deleted"


class Locale(StrEnum):
    RU = "ru"
    EN = "en"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class WorkspaceMemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class EmailVerificationPurpose(StrEnum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"
    CONNECTION_DELETE = "connection_delete"


class CrmProvider(StrEnum):
    AMOCRM = "amocrm"
    KOMMO = "kommo"
    BITRIX24 = "bitrix24"


class CrmConnectionStatus(StrEnum):
    PENDING = "pending"
    CONNECTING = "connecting"
    ACTIVE = "active"
    PAUSED = "paused"
    LOST_TOKEN = "lost_token"
    DELETING = "deleting"
    DELETED = "deleted"
    ERROR = "error"


class BillingCurrency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class BillingPlan(StrEnum):
    FREE = "free"
    PAYGO = "paygo"
    TEAM = "team"


class BillingProvider(StrEnum):
    YOOKASSA = "yookassa"
    STRIPE = "stripe"
    MANUAL = "manual"


class BillingLedgerKind(StrEnum):
    DEPOSIT = "deposit"
    CHARGE = "charge"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class TokenAccountPlan(StrEnum):
    FREE = "free"
    PAYGO = "paygo"
    START = "start"
    TEAM = "team"
    PRO = "pro"


class TokenLedgerKind(StrEnum):
    GRANT = "grant"
    PURCHASE = "purchase"
    RESERVE = "reserve"
    CHARGE = "charge"
    RELEASE = "release"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class TokenReservationStatus(StrEnum):
    RESERVED = "reserved"
    CHARGED = "charged"
    RELEASED = "released"


class JobKind(StrEnum):
    FETCH_CRM_DATA = "fetch_crm_data"
    NORMALIZE_TENANT_DATA = "normalize_tenant_data"
    REFRESH_TOKEN = "refresh_token"
    BUILD_EXPORT_ZIP = "build_export_zip"
    RUN_AUDIT_REPORT = "run_audit_report"
    ANALYZE_CONVERSATION = "analyze_conversation"
    EXTRACT_PATTERNS = "extract_patterns"
    ANONYMIZE_ARTIFACT = "anonymize_artifact"
    RETENTION_WARNING = "retention_warning"
    RETENTION_READ_ONLY = "retention_read_only"
    RETENTION_DELETE = "retention_delete"
    DELETE_CONNECTION_DATA = "delete_connection_data"
    RECALC_BALANCE = "recalc_balance"
    ISSUE_INVOICE = "issue_invoice"
    BOOTSTRAP_TENANT_SCHEMA = "bootstrap_tenant_schema"
    # Task #52 (Phase 2A): первичный pull ядра amoCRM (users/pipelines/stages/
    # leads/contacts/companies-partial). Функция — worker.jobs.crm_pull.
    # Job ставится в очередь по завершении bootstrap_tenant_schema после
    # сохранения токенов. В enum добавлен отдельным kind'ом, т.к. иначе
    # ck_job_kind CHECK constraint отклоняет INSERT при enqueue (Bug A).
    PULL_AMOCRM_CORE = "pull_amocrm_core"


class JobQueue(StrEnum):
    CRM = "crm"
    EXPORT = "export"
    AUDIT = "audit"
    AI = "ai"
    RETENTION = "retention"
    BILLING = "billing"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationKind(StrEnum):
    SYNC_COMPLETE = "sync_complete"
    SYNC_FAILED = "sync_failed"
    EXPORT_READY = "export_ready"
    AUDIT_READY = "audit_ready"
    ANALYSIS_DONE = "analysis_done"
    RETENTION_WARNING = "retention_warning"
    RETENTION_READ_ONLY = "retention_read_only"
    RETENTION_DELETED = "retention_deleted"
    BILLING_LOW = "billing_low"
    CONNECTION_LOST_TOKEN = "connection_lost_token"
    CONNECTION_DELETED = "connection_deleted"


class AdminRole(StrEnum):
    SUPERADMIN = "superadmin"
    SUPPORT = "support"
    ANALYST = "analyst"


class AdminUserStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"
    DELETED = "deleted"


class DeletionRequestStatus(StrEnum):
    AWAITING_CODE = "awaiting_code"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AiAnalysisJobKind(StrEnum):
    CALL_TRANSCRIPT = "call_transcript"
    CHAT_DIALOG = "chat_dialog"
    DEAL_REVIEW = "deal_review"


class AiAnalysisJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AiFrequencyBucket(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AiKnowledgeSource(StrEnum):
    MANUAL = "manual"
    EXTRACTED_FROM_CASES = "extracted_from_cases"
    UPLOADED_DOC = "uploaded_doc"


class AiKnowledgeStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class AiResearchConsentStatus(StrEnum):
    NOT_ASKED = "not_asked"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class AiModelProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class AiModelRunStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


# ---------- Tenant schema ----------

class CallDirection(StrEnum):
    IN = "in"
    OUT = "out"


class MessageAuthorKind(StrEnum):
    USER = "user"
    CLIENT = "client"
    SYSTEM = "system"


class StageKind(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class DealStatus(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
