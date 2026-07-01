"""Pydantic shapes for Vertretbar student billing.

Generic, provider-agnostic data shapes over the platform-owned
``student_subscriptions`` / ``grading_usage_events`` tables. The proprietary
billing logic (Stripe orchestration, subscription state machine, metering)
lives in ``benger_extended`` and reuses these shapes — so this module must not
import Stripe or encode any provider-specific behaviour.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class StudentSubscriptionRead(BaseModel):
    """Read shape for a student's subscription."""

    id: str
    user_id: str
    provider: str
    provider_customer_id: Optional[str] = None
    provider_subscription_id: Optional[str] = None
    status: str
    base_price_cents: int
    per_grading_price_cents: int
    currency: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    canceled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GradingUsageEventRead(BaseModel):
    """Read shape for a single metered grading event."""

    id: str
    user_id: str
    subscription_id: Optional[str] = None
    project_id: Optional[str] = None
    evaluation_run_id: Optional[str] = None
    event_type: str
    quantity: int
    unit_price_cents: int
    currency: str
    status: str
    occurred_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UsageSummary(BaseModel):
    """Computed usage + cost for a billing period."""

    period_start: datetime
    period_end: datetime
    grading_count: int = 0
    free_remaining: int = 0
    base_cents: int = 0
    metered_cents: int = 0
    total_cents: int = 0
    currency: str = "eur"
    events: List[GradingUsageEventRead] = Field(default_factory=list)


class InvoiceSummary(BaseModel):
    """Provider-agnostic invoice DTO (filled from the payment provider)."""

    id: str
    number: Optional[str] = None
    period: Optional[str] = None
    amount_cents: int = 0
    currency: str = "eur"
    status: Optional[str] = None
    hosted_url: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: Optional[datetime] = None
