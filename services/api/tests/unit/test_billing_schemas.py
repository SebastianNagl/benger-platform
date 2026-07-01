"""Unit tests for the platform-owned billing Pydantic shapes.

Pure (no DB): the schemas are generic data shapes over the
``student_subscriptions`` / ``grading_usage_events`` tables. The proprietary
billing logic lives in benger_extended; here we only pin ORM round-trips and
defaults so an extended overlay can rely on the contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from schemas.billing_schemas import (
    GradingUsageEventRead,
    InvoiceSummary,
    StudentSubscriptionRead,
    UsageSummary,
)


def test_subscription_read_from_orm_like_object():
    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    obj = SimpleNamespace(
        id="sub-1",
        user_id="u-1",
        provider="stripe",
        provider_customer_id="cus_1",
        provider_subscription_id="sub_1",
        status="active",
        base_price_cents=500,
        per_grading_price_cents=200,
        currency="eur",
        current_period_start=now,
        current_period_end=now,
        cancel_at_period_end=False,
        canceled_at=None,
        created_at=now,
        updated_at=None,
    )
    read = StudentSubscriptionRead.model_validate(obj)
    assert read.id == "sub-1"
    assert read.status == "active"
    assert read.base_price_cents == 500


def test_usage_event_read_from_orm_like_object():
    obj = SimpleNamespace(
        id="ev-1",
        user_id="u-1",
        subscription_id="sub-1",
        project_id="p-1",
        evaluation_run_id="run-1",
        event_type="exam_grading",
        quantity=1,
        unit_price_cents=200,
        currency="eur",
        status="reported",
        occurred_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
        reported_at=None,
    )
    read = GradingUsageEventRead.model_validate(obj)
    assert read.evaluation_run_id == "run-1"
    assert read.status == "reported"


def test_usage_summary_defaults_and_currency():
    s = UsageSummary(
        period_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert s.grading_count == 0
    assert s.free_remaining == 0
    assert s.total_cents == 0
    assert s.currency == "eur"
    assert s.events == []


def test_invoice_summary_optional_fields():
    inv = InvoiceSummary(id="in_1", amount_cents=700)
    assert inv.id == "in_1"
    assert inv.amount_cents == 700
    assert inv.currency == "eur"
    assert inv.pdf_url is None
