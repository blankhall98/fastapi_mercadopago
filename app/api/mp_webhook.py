from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import httpx

from app.core.config import settings
from app.db.session import get_db
from app.integrations.mp_webhooks import verify_mp_signature
from app.models.entitlement import Entitlement
from app.models.plan import Plan

router = APIRouter(prefix="/mp", tags=["mercado_pago"])


async def fetch_payment(payment_id: str) -> dict:
    """
    GET https://api.mercadopago.com/v1/payments/{id}
    """
    url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
    headers = {"Authorization": f"Bearer {settings.mp_access_token}"}

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            raise HTTPException(502, {"mp_status": r.status_code, "mp_response": r.text})
        return r.json()


def _extract_payment_id(body: dict, request: Request) -> str | None:
    data = body.get("data") or {}
    pid = data.get("id")
    if pid:
        return str(pid)
    # sometimes comes via query params
    pid = request.query_params.get("data.id") or request.query_params.get("id")
    return str(pid) if pid else None


@router.post("/webhook")
async def mp_webhook(request: Request, db: Session = Depends(get_db)):
    # Must be json, not bytes
    body = await request.json()

    mp_type = body.get("type")
    if mp_type != "payment":
        return {"ok": True, "ignored": True}

    payment_id = _extract_payment_id(body, request)
    if not payment_id:
        return {"ok": True, "warning": "No payment id"}

    # Signature verification (you chose to use it)
    if settings.mp_webhook_secret:
        x_signature = request.headers.get("x-signature", "")
        x_request_id = request.headers.get("x-request-id", "")
        if not x_signature or not x_request_id:
            raise HTTPException(401, "Missing signature headers")

        if not verify_mp_signature(
            secret=settings.mp_webhook_secret,
            x_signature=x_signature,
            x_request_id=x_request_id,
            data_id=payment_id,
        ):
            raise HTTPException(401, "Invalid signature")

    # Always fetch the true payment details
    payment = await fetch_payment(payment_id)

    status = payment.get("status")  # approved / pending / rejected
    external_reference = payment.get("external_reference") or ""
    metadata = payment.get("metadata") or {}

    # Best: use metadata to map to entitlement
    ent_id = metadata.get("entitlement_id")

    # Fallback: parse "ent:123" from external_reference
    if not ent_id and "ent:" in external_reference:
        try:
            parts = external_reference.split("|")
            ent_part = [p for p in parts if p.startswith("ent:")][0]
            ent_id = int(ent_part.split(":")[1])
        except Exception:
            ent_id = None

    if not ent_id:
        return {"ok": True, "warning": "Could not map entitlement"}

    ent = db.get(Entitlement, int(ent_id))
    if not ent:
        return {"ok": True, "warning": "Entitlement not found"}

    # Idempotency guard: if we already processed this payment as active
    if ent.mp_payment_id == str(payment_id) and ent.status == "active":
        return {"ok": True, "idempotent": True}

    # Save the last seen payment id
    ent.mp_payment_id = str(payment_id)

    if status == "approved":
        plan = db.get(Plan, ent.plan_id)

        ent.status = "active"

        # one-time => set expiry
        if plan and plan.kind == "one_time" and plan.access_duration_days:
            ent.expires_at = datetime.now(timezone.utc) + timedelta(days=int(plan.access_duration_days))

        db.commit()
        return {"ok": True, "activated": True}

    # Not approved -> do not grant access (keep inactive)
    ent.status = "inactive"
    db.commit()
    return {"ok": True, "activated": False, "mp_status": status, "ent_status": ent.status}
