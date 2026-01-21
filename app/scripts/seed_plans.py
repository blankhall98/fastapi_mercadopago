from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.plan import Plan

PLANS = [
    # One-Time Memberships
    {
        "code": "one_time_30d", "name": "One-time 30 Days", "kind": "one_time",
        "price": 300.00, "currency": "MXN", "access_duration_days": 30
    },
    {"code": "one_time_365d", "name": "One-time 365 days", "kind": "one_time", "price": 1990.00, "currency": "MXN", "access_duration_days": 365},

    # Recurring Memberships
    {"code": "recurring_monthly", "name": "Recurring Monthly", "kind": "recurring", "price": 179.00, "currency": "MXN", "access_duration_days": None},
    {"code": "recurring_annual", "name": "Recurring Annual", "kind": "recurring", "price": 1790.00, "currency": "MXN", "access_duration_days": None},
]

def upsert_plan(db: Session, data: dict) -> Plan:
    pass