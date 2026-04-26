"""
ORM-модели шаблона tenant-schema (``crm_<provider>_<shortid>``).

Эти таблицы создаются внутри каждой активной tenant-схемы. Alembic применяет
их **без** schema-префикса (через ``SET search_path = "<schema>", public``
в ``env.py``), поэтому здесь НИ в коем случае не указываем ``schema=...``.

См. ``docs/db/SCHEMA.md`` Часть 2.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP

from .base import TenantBase
from .enums import CallDirection, MessageAuthorKind, StageKind
from ._helpers import JSONB, UUID, enum_check, now_default, uuid_pk

TZ = TIMESTAMP(timezone=True)


# =========================================================================
# Raw tables (single JSONB payload as came from CRM)
# =========================================================================

def _raw_columns() -> list:
    """Набор колонок raw-таблицы — одинаков для всех."""
    return [
        Column("external_id", Text, nullable=False),
        Column("payload", JSONB, nullable=False),
        Column(
            "fetched_at",
            TZ,
            nullable=False,
            server_default=now_default(),
        ),
        Column("source_event_id", Text, nullable=True),
    ]


class RawDeal(TenantBase):
    __tablename__ = "raw_deals"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawContact(TenantBase):
    __tablename__ = "raw_contacts"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawCompany(TenantBase):
    __tablename__ = "raw_companies"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawTask(TenantBase):
    __tablename__ = "raw_tasks"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawNote(TenantBase):
    __tablename__ = "raw_notes"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawEvent(TenantBase):
    __tablename__ = "raw_events"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawCall(TenantBase):
    __tablename__ = "raw_calls"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawChat(TenantBase):
    __tablename__ = "raw_chats"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawMessage(TenantBase):
    __tablename__ = "raw_messages"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawUser(TenantBase):
    __tablename__ = "raw_users"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawPipeline(TenantBase):
    __tablename__ = "raw_pipelines"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawStage(TenantBase):
    __tablename__ = "raw_stages"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawProduct(TenantBase):
    __tablename__ = "raw_products"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


class RawTag(TenantBase):
    __tablename__ = "raw_tags"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())
    source_event_id = Column(Text, nullable=True)


# =========================================================================
# Normalized tables
# =========================================================================

class Pipeline(TenantBase):
    __tablename__ = "pipelines"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    is_default = Column(Boolean, nullable=False, server_default=text("FALSE"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class Stage(TenantBase):
    __tablename__ = "stages"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    pipeline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id"),
        nullable=False,
    )
    name = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=True)
    kind = Column(Text, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("kind", StageKind, name="ck_stages_kind"),
        Index("ix_stages_pipeline_sort", "pipeline_id", "sort_order"),
    )


class CrmUser(TenantBase):
    __tablename__ = "crm_users"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    full_name = Column(Text, nullable=True)
    email_hash = Column(Text, nullable=True)
    role = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class Company(TenantBase):
    __tablename__ = "companies"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    name = Column(Text, nullable=True)
    inn_hash = Column(Text, nullable=True)
    created_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class Contact(TenantBase):
    __tablename__ = "contacts"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    full_name = Column(Text, nullable=True)
    phone_primary_hash = Column(Text, nullable=True)
    email_primary_hash = Column(Text, nullable=True)
    responsible_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_users.id"),
        nullable=True,
    )
    created_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_contacts_phone", "phone_primary_hash"),
        Index("ix_contacts_email", "email_primary_hash"),
        Index("ix_contacts_resp_user", "responsible_user_id"),
    )


class Deal(TenantBase):
    __tablename__ = "deals"

    id = uuid_pk()
    external_id = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=True)
    pipeline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id"),
        nullable=True,
    )
    stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id"), nullable=True)
    status = Column(Text, nullable=True)
    responsible_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_users.id"),
        nullable=True,
    )
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    price_cents = Column(BigInteger, nullable=True)
    currency = Column(Text, nullable=True)
    created_at_external = Column(TZ, nullable=True)
    updated_at_external = Column(TZ, nullable=True)
    closed_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','won','lost') OR status IS NULL",
            name="ck_deals_status",
        ),
        Index("ix_deals_pipeline_stage", "pipeline_id", "stage_id"),
        Index("ix_deals_status", "status"),
        Index("ix_deals_resp_user", "responsible_user_id"),
    )


class Task(TenantBase):
    __tablename__ = "tasks"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=True)
    responsible_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_users.id"),
        nullable=True,
    )
    kind = Column(Text, nullable=True)
    text_body = Column("text", Text, nullable=True)
    is_completed = Column(Boolean, nullable=False, server_default=text("FALSE"))
    due_at_external = Column(TZ, nullable=True)
    completed_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_tasks_deal", "deal_id"),
        Index("ix_tasks_resp_completed", "responsible_user_id", "is_completed"),
        Index("ix_tasks_due", "due_at_external"),
    )


class Note(TenantBase):
    __tablename__ = "notes"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_users.id"),
        nullable=True,
    )
    body = Column(Text, nullable=True)
    created_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class Call(TenantBase):
    __tablename__ = "calls"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_users.id"),
        nullable=True,
    )
    direction = Column(Text, nullable=True)
    duration_sec = Column(Integer, nullable=True)
    result = Column(Text, nullable=True)
    started_at_external = Column(TZ, nullable=True)
    transcript_ref = Column(JSONB, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("direction", CallDirection, name="ck_calls_direction"),
        Index("ix_calls_deal", "deal_id"),
        Index("ix_calls_user_started", "user_id", "started_at_external"),
    )


class Chat(TenantBase):
    __tablename__ = "chats"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    channel = Column(Text, nullable=True)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    started_at_external = Column(TZ, nullable=True)
    closed_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class Message(TenantBase):
    __tablename__ = "messages"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), nullable=True)
    author_kind = Column(Text, nullable=True)
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("crm_users.id"),
        nullable=True,
    )
    text_body = Column("text", Text, nullable=True)
    sent_at_external = Column(TZ, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        enum_check("author_kind", MessageAuthorKind, name="ck_messages_author_kind"),
        Index("ix_messages_chat_sent", "chat_id", "sent_at_external"),
    )


class Product(TenantBase):
    __tablename__ = "products"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    name = Column(Text, nullable=True)
    price_cents = Column(BigInteger, nullable=True)
    currency = Column(Text, nullable=True)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class Tag(TenantBase):
    __tablename__ = "tags"

    id = uuid_pk()
    external_id = Column(Text, nullable=True, unique=True)
    name = Column(Text, nullable=False)
    fetched_at = Column(TZ, nullable=False, server_default=now_default())


class DealTag(TenantBase):
    __tablename__ = "deal_tags"

    deal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("deal_id", "tag_id", name="pk_deal_tags"),
    )


class DealProduct(TenantBase):
    __tablename__ = "deal_products"

    deal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
        nullable=True,
    )
    external_id = Column(Text, nullable=False)
    catalog_id = Column(Text, nullable=True)
    quantity = Column(Numeric(18, 4), nullable=True)
    price_cents = Column(BigInteger, nullable=True)
    price_id = Column(Text, nullable=True)
    raw_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        PrimaryKeyConstraint("deal_id", "external_id", name="pk_deal_products"),
        Index("ix_deal_products_product", "product_id"),
        Index("ix_deal_products_catalog", "catalog_id"),
    )


class DealContact(TenantBase):
    __tablename__ = "deal_contacts"

    deal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_primary = Column(Boolean, nullable=False, server_default=text("FALSE"))
    raw_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        PrimaryKeyConstraint("deal_id", "contact_id", name="pk_deal_contacts"),
        Index("ix_deal_contacts_contact", "contact_id"),
    )


class DealCompany(TenantBase):
    __tablename__ = "deal_companies"

    deal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_primary = Column(Boolean, nullable=False, server_default=text("FALSE"))
    raw_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        PrimaryKeyConstraint("deal_id", "company_id", name="pk_deal_companies"),
        Index("ix_deal_companies_company", "company_id"),
    )


class DealStageTransition(TenantBase):
    __tablename__ = "deal_stage_transitions"

    id = uuid_pk()
    deal_id = Column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    event_external_id = Column(Text, nullable=False, unique=True)
    from_stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id"), nullable=True)
    to_stage_id = Column(UUID(as_uuid=True), ForeignKey("stages.id"), nullable=True)
    changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("crm_users.id"), nullable=True)
    changed_at_external = Column(TZ, nullable=True)
    raw_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_deal_stage_transitions_deal_time", "deal_id", "changed_at_external"),
        Index("ix_deal_stage_transitions_to_stage", "to_stage_id"),
    )


class DealSource(TenantBase):
    __tablename__ = "deal_sources"

    deal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_name = Column(Text, nullable=True)
    source_type = Column(Text, nullable=True)
    utm_source = Column(Text, nullable=True)
    utm_medium = Column(Text, nullable=True)
    utm_campaign = Column(Text, nullable=True)
    utm_content = Column(Text, nullable=True)
    utm_term = Column(Text, nullable=True)
    raw_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        PrimaryKeyConstraint("deal_id", name="pk_deal_sources"),
        Index("ix_deal_sources_source", "source_name"),
        Index("ix_deal_sources_utm", "utm_source", "utm_medium", "utm_campaign"),
    )


class CrmCustomField(TenantBase):
    __tablename__ = "crm_custom_fields"

    id = uuid_pk()
    entity_type = Column(Text, nullable=False)
    external_id = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    code = Column(Text, nullable=True)
    field_type = Column(Text, nullable=True)
    raw_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        UniqueConstraint("entity_type", "external_id", name="uq_crm_custom_fields_entity_external"),
        Index("ix_crm_custom_fields_entity", "entity_type"),
    )


class CrmCustomFieldValue(TenantBase):
    __tablename__ = "crm_custom_field_values"

    id = uuid_pk()
    entity_type = Column(Text, nullable=False)
    entity_external_id = Column(Text, nullable=False)
    custom_field_id = Column(UUID(as_uuid=True), ForeignKey("crm_custom_fields.id"), nullable=True)
    field_external_id = Column(Text, nullable=False)
    field_name = Column(Text, nullable=True)
    value_text = Column(Text, nullable=True)
    value_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fetched_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_external_id",
            "field_external_id",
            name="uq_crm_custom_field_values_entity_field",
        ),
        Index("ix_crm_custom_field_values_field", "custom_field_id"),
        Index("ix_crm_custom_field_values_entity", "entity_type", "entity_external_id"),
    )


class KnowledgeBaseVersion(TenantBase):
    __tablename__ = "knowledge_base_versions"

    id = uuid_pk()
    version = Column(Integer, nullable=False, unique=True)
    content = Column(Text, nullable=False)
    meta = Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at = Column(TZ, nullable=False, server_default=now_default())

    __table_args__ = (
        Index("ix_kbversion_active_created", "is_active", text("created_at DESC")),
    )
