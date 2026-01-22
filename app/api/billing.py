from uuid import uuid4

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
        "items": [],
        #important: your own stable reference
        "external_reference": "",
        #Metadata for later identification
        "metadata": {},
        #MP notifications
        "notification_url": settings.mp_webhook_url,
        "back_urls": {},
        "auto_return": "approved",
    }

    sdk = mp_sdk()

    #create preference item
    result = sdk.preference().create(preference_data)
    resp = result("response") or {}
    status = result("status")

    if status not in (200, 201):
        raise HTTPException(502, {"mp_status": status, "mp_response": resp})
    