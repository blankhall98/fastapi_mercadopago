from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.entitlement import Entitlement
from app.models.plan import Plan
from app.models.user import User

from app.utils.dt import as_utc_aware

def require_active_entitlement(plan_codes: list[str] | None = None):
    def _dep(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        q = db.query(Entitlement).join(Plan, Plan.id == Entitlement.plan_id).filter(
            Entitlement.user_id == user.id,
            Entitlement.status.in_(("active", "canceled")),
        )
        if plan_codes:
            q = q.filter(Plan.code.in_(plan_codes))

        ent = q.first()
        if not ent:
            raise HTTPException(status_code=402, detail="Active entitlement required")
        
        now = datetime.now(timezone.utc)
        exp = as_utc_aware(ent.expires_at) if ent.expires_at else None

        if ent.status == "canceled" and not exp:
            raise HTTPException(status_code=402, detail="Entitlement has expired")

        if exp and exp < now:
            raise HTTPException(status_code=402, detail="Entitlement has expired")
        
        return ent
    return _dep
