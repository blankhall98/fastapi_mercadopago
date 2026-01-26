from fastapi import APIRouter, Depends
from app.api.deps_billing import require_active_entitlement

router = APIRouter(prefix="/premium", tags=["premium"])

@router.get("/premium-feature")
def premium_feature(ent = Depends(require_active_entitlement())):
    return {"ok": True, "message": "You have premium access!", "entitlement_id": ent.id}