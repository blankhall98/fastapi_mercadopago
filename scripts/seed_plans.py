from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.plan import Plan

PLANS = [
    # One-Time Memberships
    {
        "code": "one_time_30d", "name": "One-time 30 Days", "kind": "one_time",
        "price": 1.00, "currency": "MXN", "access_duration_days": 30
    },

    {"code": "one_time_365d", "name": "One-time 365 days", "kind": "one_time",
      "price": 10.00, "currency": "MXN", "access_duration_days": 365},

    # Recurring Memberships
    {"code": "recurring_monthly", "name": "Recurring Monthly",
      "kind": "recurring", "price": 1.00, "currency": "MXN",
        "access_duration_days": None,
        "interval_count": 1, "interval_unit": "months"},

    {"code": "recurring_annual", "name": "Recurring Annual",
      "kind": "recurring", "price": 10.00, "currency": "MXN",
        "access_duration_days": None,
        "interval_count": 12, "interval_unit": "months"},
]

def upsert_plan(db: Session, data: dict) -> Plan:
    plan = db.query(Plan).filter(Plan.code == data["code"]).first()
    if plan:
        for k, v in data.items():
            setattr(plan, k, v)
        return plan
    
    plan = Plan(**data)
    db.add(plan)
    return plan

def main():
    db = SessionLocal()
    try:
        for data in PLANS:
            upsert_plan(db, data)
        db.commit()
        print("Seeded plans:", [p["code"] for p in PLANS])
    finally:
        db.close()

if __name__ == "__main__":
    main()