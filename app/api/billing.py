from uuid import uuid4
from datetime import datetime, timezone
from app.utils.dt import as_utc_aware

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.plan import Plan
from app.models.entitlement import Entitlement
from app.integrations.mercadopago_client import mp_sdk
from app.schemas.billing import PlanOut, CreateOneTimeLinkIn, CreateOneTimeLinkOut
from app.models.user import User

router = APIRouter(prefix="/billing", tags=["billing"])

# Display available subscription plans
@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    return db.query(Plan).order_by(Plan.kind, Plan.price).all()

# Create a one-time payment link
@router.post("/one-time/link", response_model=CreateOneTimeLinkOut)
def create_one_time_payment_link(
    payload: CreateOneTimeLinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = db.query(Plan).filter(Plan.code == payload.plan_code).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.kind != "one_time":
        raise HTTPException(status_code=400, detail="Plan is not a one-time payment plan")
    
    #Order ID generation
    order_id = str(uuid4())

    #Create or reuse entitlement row for this user+plan
    ent = db.query(Entitlement).filter(
        Entitlement.user_id == user.id,
        Entitlement.plan_id == plan.id
    ).first()

    if not ent:
        ent = Entitlement(user_id=user.id, plan_id=plan.id, status="inactive")
        db.add(ent)
        db.flush() #assigns ent.id without committing

    # Preference payload (checkout PRO)
    preference_data = {
        "items": [
            {
                "title": plan.name,
                "quantity": 1,
                "unit_price": float(plan.price),
                "currency_id": plan.currency or settings.mp_currency,
            }
        ],
        #important: your own stable reference
        "external_reference": f"user:{user.id}|ent:{ent.id}|order:{order_id}|plan:{plan.code}",
        #Metadata for later identification
        "metadata": {
            "user_id": user.id,
            "entitlement_id": ent.id,
            "order_id": order_id,
            "plan_code": plan.code,
        },
        #MP notifications
        "notification_url": settings.mp_webhook_url,
        "back_urls": {
            "success": f"{settings.app_base_url}/billing/success",
            "failure": f"{settings.app_base_url}/billing/failure",
            "pending": f"{settings.app_base_url}/billing/pending",
        },
        "auto_return": "approved",
    }

    sdk = mp_sdk()

    #create preference item
    result = sdk.preference().create(preference_data)
    resp = result.get("response") or {}
    status = result.get("status")

    if status not in (200, 201):
        raise HTTPException(502, {"mp_status": status, "mp_response": resp})
    
    preference_id = resp.get("id")
    init_point = resp.get("sandbox_init_point") or resp.get("init_point")
    if not preference_id or not init_point:
        raise HTTPException(502, {"mp_response": resp})
    
    #Store MP reference (still inactive until webhook confirms payment)
    ent.mp_preference_id = preference_id
    db.commit()

    return CreateOneTimeLinkOut(preference_id=preference_id, init_point=init_point)

@router.get("/me")
def my_billing(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ents = (db.query(Entitlement, Plan)
            .join(Plan, Plan.id == Entitlement.plan_id)
            .filter(Entitlement.user_id == user.id)
            .all()
            )
    
    now = datetime.now(timezone.utc)

    out = []
    for ent, plan in ents:
        exp = as_utc_aware(ent.expires_at)
        is_active = ent.status == "active" and (exp is None or exp > now)
        out.append({
            "plan_code": plan.code,
            "plan_kind": plan.kind,
            "status": ent.status,
            "expires_at": exp.isoformat() if exp else None,
            "mp_payment_id": ent.mp_payment_id,
            "mp_preference_id": ent.mp_preference_id,
            "mp_preapproval_id": ent.mp_preapproval_id,
            "is_active_now": is_active,
        })

    return {"user_id": user.id, "entitlements": out}