import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import EmailStr
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Domain — core entity for the CartoGraph intelligence database
# ---------------------------------------------------------------------------


class Domain(SQLModel, table=True):
    """
    Primary domain record. JSONB columns hold all enrichment field groups.
    Use the Alembic migration (b4e1f2a3c9d8) to create this table — do NOT
    rely on SQLModel autogenerate for the GIN indexes.
    """

    __tablename__ = "domains"  # type: ignore[assignment]

    domain_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True
    )
    domain: str = Field(max_length=255, unique=True, index=True)
    country: str = Field(default="UK", max_length=2)
    tld: str | None = Field(default=None, max_length=20)
    status: str = Field(default="active", max_length=20)
    first_seen_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    last_updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    schema_version: str = Field(default="1.0.0", max_length=10)

    # JSONB enrichment groups — typed as Any to allow arbitrary nested dicts
    discovery: Any = Field(default=None, sa_column=Column(JSONB))
    ecommerce: Any = Field(default=None, sa_column=Column(JSONB))
    seo_metrics: Any = Field(default=None, sa_column=Column(JSONB))
    intent_layer: Any = Field(default=None, sa_column=Column(JSONB))
    serp_intelligence: Any = Field(default=None, sa_column=Column(JSONB))
    technical_layer: Any = Field(default=None, sa_column=Column(JSONB))
    contact: Any = Field(default=None, sa_column=Column(JSONB))
    marketplace_overlap: Any = Field(default=None, sa_column=Column(JSONB))
    paid_ads_presence: Any = Field(default=None, sa_column=Column(JSONB))
    meta: Any = Field(default=None, sa_column=Column(JSONB))
    change_tracking: Any = Field(default=None, sa_column=Column(JSONB))
    confidence_score: Any = Field(default=None, sa_column=Column(JSONB))
    pipeline: Any = Field(default=None, sa_column=Column(JSONB))
    ai_summary: Any = Field(default=None, sa_column=Column(JSONB))


# API response models — omit JSONB blobs by default for list endpoints


class DomainSummary(SQLModel):
    """Lightweight domain record for list/table views."""

    domain_id: uuid.UUID
    domain: str
    country: str
    tld: str | None = None
    status: str
    first_seen_at: datetime
    last_updated_at: datetime
    schema_version: str
    # Flattened scalar fields from JSONB for fast filtering
    domain_rating: int | None = None
    organic_traffic_estimate: int | None = None
    commercial_intent_score: int | None = None
    platform: str | None = None
    category_primary: str | None = None
    confidence_value: float | None = None


class DomainPublic(SQLModel):
    """Full domain record including all JSONB groups."""

    domain_id: uuid.UUID
    domain: str
    country: str
    tld: str | None = None
    status: str
    first_seen_at: datetime
    last_updated_at: datetime
    schema_version: str
    discovery: Any = None
    ecommerce: Any = None
    seo_metrics: Any = None
    intent_layer: Any = None
    serp_intelligence: Any = None
    technical_layer: Any = None
    contact: Any = None
    marketplace_overlap: Any = None
    paid_ads_presence: Any = None
    meta: Any = None
    change_tracking: Any = None
    confidence_score: Any = None
    pipeline: Any = None
    ai_summary: Any = None


class DomainsPublic(SQLModel):
    data: list[DomainSummary]
    count: int
    page: int = 1
    next_cursor: str | None = None  # cursor-pagination token


# ---------------------------------------------------------------------------
# Workspace — team/account container; owns tier + API token
# ---------------------------------------------------------------------------


class Workspace(SQLModel, table=True):
    __tablename__ = "workspace"  # type: ignore[assignment]

    workspace_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    tier: str = Field(default="free", max_length=20)
    api_token_hash: str | None = Field(default=None, max_length=255)
    api_token_prefix: str | None = Field(default=None, max_length=16)
    # Monthly usage counters
    domain_lookups_used: int = Field(default=0)
    export_credits_used: int = Field(default=0)
    api_calls_used: int = Field(default=0)
    billing_cycle_start: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    # Stripe billing
    stripe_customer_id: str | None = Field(default=None, max_length=255)
    stripe_subscription_id: str | None = Field(default=None, max_length=255)
    stripe_subscription_status: str | None = Field(default=None, max_length=64)
    stripe_price_id: str | None = Field(default=None, max_length=255)
    founding_member: bool = Field(default=False)
    # Timestamps
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    webhooks: list["WebhookEndpoint"] = Relationship(back_populates="workspace", cascade_delete=True)
    alerts: list["Alert"] = Relationship(back_populates="workspace", cascade_delete=True)


class WorkspaceCreate(SQLModel):
    name: str = Field(max_length=255)


class WorkspacePublic(SQLModel):
    workspace_id: uuid.UUID
    name: str
    tier: str
    api_token_prefix: str | None = None
    domain_lookups_used: int
    export_credits_used: int
    api_calls_used: int
    billing_cycle_start: datetime
    stripe_subscription_status: str | None = None
    founding_member: bool = False
    created_at: datetime


# ---------------------------------------------------------------------------
# WebhookEndpoint — user-configured delivery targets
# ---------------------------------------------------------------------------


class WebhookEndpoint(SQLModel, table=True):
    __tablename__ = "webhook_endpoint"  # type: ignore[assignment]

    webhook_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.workspace_id", nullable=False, ondelete="CASCADE")
    url: str = Field(max_length=2048)
    secret: str = Field(max_length=255)  # HMAC-SHA256 signing secret
    event_types: Any = Field(default=None, sa_column=Column(JSONB))  # list of event type strings
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    workspace: Workspace | None = Relationship(back_populates="webhooks")


class WebhookCreate(SQLModel):
    url: str = Field(max_length=2048)
    event_types: list[str] = Field(default_factory=list)


class WebhookPublic(SQLModel):
    webhook_id: uuid.UUID
    workspace_id: uuid.UUID
    url: str
    event_types: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Alert — saved alert configurations
# ---------------------------------------------------------------------------


class Alert(SQLModel, table=True):
    __tablename__ = "alert"  # type: ignore[assignment]

    alert_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.workspace_id", nullable=False, ondelete="CASCADE")
    name: str = Field(max_length=255)
    alert_type: str = Field(max_length=64)  # new_domain | tech_change | dr_change | serp_feature
    filter_criteria: Any = Field(default=None, sa_column=Column(JSONB))
    threshold: Any = Field(default=None, sa_column=Column(JSONB))
    delivery: Any = Field(default=None, sa_column=Column(JSONB))  # {email, webhook_id, slack_url}
    is_active: bool = Field(default=True)
    last_triggered: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-arg]
    )
    workspace: Workspace | None = Relationship(back_populates="alerts")


class AlertCreate(SQLModel):
    name: str = Field(max_length=255)
    alert_type: str = Field(max_length=64)
    filter_criteria: dict[str, Any] | None = None
    threshold: dict[str, Any] | None = None
    delivery: dict[str, Any] | None = None


class AlertPublic(SQLModel):
    alert_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    alert_type: str
    filter_criteria: dict[str, Any] | None = None
    threshold: dict[str, Any] | None = None
    is_active: bool
    last_triggered: datetime | None = None
    created_at: datetime
