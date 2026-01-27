import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.integrations.mp_webhooks import verify_mp_signature
from app.models.entitlement import Entitlement
from app.models.plan import Plan

router = APIRouter(prefix="/mp", tags=["mercado_pago"])

MP_API_BASE = "https://api.mercadopago.com"


# ---------------------------
# MP HTTP helpers
# ---------------------------

async def mp_get_json(path: str) -> dict[str, Any]:
    url = f"{MP_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {settings.mp_access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            # keep body as text to avoid json decode surprises
            raise HTTPException(502, {"mp_status": r.status_code, "mp_response": r.text, "url": url})
        return r.json()


async def fetch_payment(payment_id: str) -> dict[str, Any]:
    return await mp_get_json(f"/v1/payments/{payment_id}")


async def fetch_merchant_order(merchant_order_id: str) -> dict[str, Any]:
    return await mp_get_json(f"/merchant_orders/{merchant_order_id}")


async def fetch_preapproval(preapproval_id: str) -> dict[str, Any]:
    return await mp_get_json(f"/preapproval/{preapproval_id}")


async def fetch_authorized_payment(authorized_payment_id: str) -> dict[str, Any]:
    return await mp_get_json(f"/authorized_payments/{authorized_payment_id}")


# ---------------------------
# parsing helpers
# ---------------------------

def _safe_int(x: Any) -> int | None:
    try:
        return int(x)
    except Exception:
        return None


def _parse_entitlement_id_from_external_reference(external_reference: str) -> int | None:
    # "user:1|ent:2|order:...|plan:..."
    if "ent:" not in external_reference:
        return None
    try:
        parts = external_reference.split("|")
        ent_part = [p for p in parts if p.startswith("ent:")][0]
        return int(ent_part.split(":")[1])
    except Exception:
        return None


def _extract_entitlement_id_from_payment(payment: dict[str, Any]) -> int | None:
    metadata = payment.get("metadata") or {}
    ent_id = _safe_int(metadata.get("entitlement_id"))
    if ent_id:
        return ent_id

    external_reference = payment.get("external_reference") or ""
    return _parse_entitlement_id_from_external_reference(external_reference)


def _extract_entitlement_id_from_preapproval(pre: dict[str, Any]) -> int | None:
    metadata = pre.get("metadata") or {}
    ent_id = _safe_int(metadata.get("entitlement_id"))
    if ent_id:
        return ent_id

    external_reference = pre.get("external_reference") or ""
    return _parse_entitlement_id_from_external_reference(external_reference)


def _pick_latest_payment_id_from_merchant_order(mo: dict[str, Any]) -> str | None:
    payments = mo.get("payments") or []
    # payments usually list objects with id/status
    for p in reversed(payments):
        pid = p.get("id")
        if pid:
            return str(pid)
    return None


async def _resolve_payment_id_from_merchant_order(
    merchant_order_id: str,
    attempts: int = 10,
    base_delay_seconds: float = 1.2,
) -> tuple[str | None, dict[str, Any]]:
    """
    MP may send merchant_order before payments[] is populated.
    We do short polling.
    """
    last_mo: dict[str, Any] = {}
    for i in range(attempts):
        mo = await fetch_merchant_order(merchant_order_id)
        last_mo = mo

        pid = _pick_latest_payment_id_from_merchant_order(mo)
        if pid:
            return pid, mo

        # exponential-ish backoff
        await asyncio.sleep(base_delay_seconds * (1.0 + i * 0.35))

    return None, last_mo


def _maybe_verify_signature(request: Request, data_id: str) -> None:
    """
    Verify MP signature only if:
    - mp_webhook_secret is configured
    - required headers exist
    Sandbox + some topics may omit headers.
    """
    if not getattr(settings, "mp_webhook_secret", None):
        return

    x_signature = request.headers.get("x-signature", "")
    x_request_id = request.headers.get("x-request-id", "")

    if not x_signature or not x_request_id:
        print("MP signature headers missing; skipping verification for this request.")
        return

    ok = verify_mp_signature(
        secret=settings.mp_webhook_secret,
        x_signature=x_signature,
        x_request_id=x_request_id,
        data_id=str(data_id),
    )
    if not ok:
        raise HTTPException(401, "Invalid signature")


def _extract_id_from_resource_url(resource: str, needle: str) -> str | None:
    """
    resource examples:
    - https://api.mercadolibre.com/merchant_orders/123
    - https://api.mercadopago.com/preapproval/456
    """
    if not resource:
        return None
    if needle not in resource:
        return None
    try:
        return resource.rstrip("/").split("/")[-1]
    except Exception:
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


# ---------------------------
# core processors
# ---------------------------

async def _process_payment(payment_id: str, payment: dict[str, Any], db: Session) -> dict[str, Any]:
    status = payment.get("status")  # approved / pending / rejected
    status_detail = payment.get("status_detail")

    print("MP payment_id:", payment_id)
    print("MP status:", status)
    print("MP status_detail:", status_detail)
    print("MP payment_method_id:", payment.get("payment_method_id"))
    print("MP payment_type_id:", payment.get("payment_type_id"))

    ent_id = _extract_entitlement_id_from_payment(payment)
    if not ent_id:
        return {"ok": True, "warning": "Could not map entitlement (payment)"}

    ent = db.get(Entitlement, int(ent_id))
    if not ent:
        return {"ok": True, "warning": "Entitlement not found (payment)"}

    # idempotency
    if ent.mp_payment_id == str(payment_id) and ent.status == "active":
        return {"ok": True, "idempotent": True}

    ent.mp_payment_id = str(payment_id)

    if status == "approved":
        plan = db.get(Plan, ent.plan_id)
        ent.status = "active"

        # one_time -> expiry
        if plan and plan.kind == "one_time" and plan.access_duration_days:
            ent.expires_at = datetime.now(timezone.utc) + timedelta(days=int(plan.access_duration_days))
        else:
            # recurring via payment doesn't set expires; keep None
            pass

        db.commit()
        return {"ok": True, "activated": True}

    # not approved => no access
    ent.status = "inactive"
    db.commit()
    return {"ok": True, "activated": False, "mp_status": status, "mp_status_detail": status_detail}


async def _process_preapproval(preapproval_id: str, pre: dict[str, Any], db: Session) -> dict[str, Any]:
    status = pre.get("status")  # authorized / paused / cancelled / pending
    reason = pre.get("reason")
    print("MP preapproval_id:", preapproval_id)
    print("MP preapproval status:", status)
    print("MP preapproval reason:", reason)

    ent_id = _extract_entitlement_id_from_preapproval(pre)
    if not ent_id:
        return {"ok": True, "warning": "Could not map entitlement (preapproval)"}

    ent = db.get(Entitlement, int(ent_id))
    if not ent:
        return {"ok": True, "warning": "Entitlement not found (preapproval)"}

    ent.mp_preapproval_id = str(preapproval_id)

    auto = pre.get("auto_recurring") or {}
    end_date = auto.get("end_date") or pre.get("next_payment_date")
    end_dt = _parse_iso_datetime(end_date)

    # Our gating truth: active only when authorized/active
    if status in ("authorized", "active"):
        ent.status = "active"
        # keep local period end in sync if MP provides it
        if end_dt:
            ent.expires_at = end_dt
    elif status in ("cancelled", "canceled"):
        ent.status = "canceled"
        ent.expires_at = end_dt or ent.expires_at
    elif status == "paused":
        ent.status = "inactive"
        ent.expires_at = None
    else:
        # pending / etc -> keep inactive
        ent.status = "inactive"

    db.commit()
    return {"ok": True, "topic": "preapproval", "mp_status": status, "ent_status": ent.status}


async def _process_authorized_payment(
    authorized_payment_id: str,
    auth: dict[str, Any],
    db: Session,
) -> dict[str, Any]:
    payment = auth.get("payment") or {}
    payment_id = payment.get("id")
    payment_status = payment.get("status")
    payment_status_detail = payment.get("status_detail")
    preapproval_id = auth.get("preapproval_id")

    print("MP authorized_payment_id:", authorized_payment_id)
    print("MP authorized_payment status:", auth.get("status"))
    print("MP payment_id:", payment_id)
    print("MP payment_status:", payment_status)
    print("MP payment_status_detail:", payment_status_detail)

    ent_id: int | None = None
    end_dt: datetime | None = None
    pre: dict[str, Any] | None = None
    external_reference = str(auth.get("external_reference") or "")
    if external_reference:
        ent_id = _parse_entitlement_id_from_external_reference(external_reference)

    if preapproval_id:
        pre = await fetch_preapproval(str(preapproval_id))
        if not ent_id:
            ent_id = _extract_entitlement_id_from_preapproval(pre)
        auto = pre.get("auto_recurring") or {}
        end_date = auto.get("end_date") or pre.get("next_payment_date")
        end_dt = _parse_iso_datetime(end_date)

    if not ent_id:
        return {"ok": True, "warning": "Could not map entitlement (authorized_payment)"}

    ent = db.get(Entitlement, int(ent_id))
    if not ent:
        return {"ok": True, "warning": "Entitlement not found (authorized_payment)"}

    if preapproval_id:
        ent.mp_preapproval_id = str(preapproval_id)
    if payment_id:
        ent.mp_payment_id = str(payment_id)

    if payment_status == "approved":
        ent.status = "active"
        if end_dt:
            ent.expires_at = end_dt
    elif payment_status in ("rejected", "cancelled"):
        ent.status = "past_due"
    elif payment_status in ("refunded", "charged_back"):
        ent.status = "inactive"

    db.commit()
    return {
        "ok": True,
        "topic": "subscription_authorized_payment",
        "payment_status": payment_status,
        "payment_status_detail": payment_status_detail,
        "ent_status": ent.status,
    }


# ---------------------------
# webhook endpoint
# ---------------------------

@router.post("/webhook")
async def mp_webhook(request: Request, db: Session = Depends(get_db)):
    qp = dict(request.query_params)
    try:
        body = await request.json()
    except Exception:
        body = {}

    print("WEBHOOK HIT", qp)
    print("WEBHOOK BODY", body)

    topic = request.query_params.get("topic") or body.get("topic")
    mp_type = body.get("type") or request.query_params.get("type")
    resource = body.get("resource") or ""
    data = body.get("data") or {}

    # 1) Recurring subscriptions: preapproval
    # MP can send topic=preapproval or type=preapproval
    if topic in ("preapproval", "subscription_preapproval") or mp_type in ("preapproval", "subscription_preapproval"):
        preapproval_id = (
            request.query_params.get("id")
            or data.get("id")
            or request.query_params.get("data.id")
            or _extract_id_from_resource_url(resource, "preapproval")
        )
        if not preapproval_id:
            return {"ok": True, "ignored": "preapproval_no_id"}

        _maybe_verify_signature(request, data_id=str(preapproval_id))

        pre = await fetch_preapproval(str(preapproval_id))
        return await _process_preapproval(str(preapproval_id), pre, db)

    # 1b) Recurring subscription payments (authorized payments)
    if topic == "subscription_authorized_payment" or mp_type == "subscription_authorized_payment":
        authorized_payment_id = (
            request.query_params.get("id")
            or data.get("id")
            or request.query_params.get("data.id")
            or _extract_id_from_resource_url(resource, "authorized_payments")
        )
        if not authorized_payment_id:
            return {"ok": True, "ignored": "authorized_payment_no_id"}

        _maybe_verify_signature(request, data_id=str(authorized_payment_id))
        auth = await fetch_authorized_payment(str(authorized_payment_id))
        return await _process_authorized_payment(str(authorized_payment_id), auth, db)

    # 2) One-time payments / payment events
    payment_id: str | None = None

    # 2a) Direct payment event
    if mp_type == "payment" or request.query_params.get("type") == "payment":
        payment_id = data.get("id") or request.query_params.get("data.id") or request.query_params.get("id")
        payment_id = str(payment_id) if payment_id else None

    # 2b) Merchant order event (IPN style)
    if not payment_id and topic == "merchant_order":
        merchant_order_id = request.query_params.get("id") or _extract_id_from_resource_url(resource, "merchant_orders")
        if not merchant_order_id:
            return {"ok": True, "ignored": "merchant_order_no_id"}

        # Note: merchant_order signature headers are often missing in sandbox -> optional
        _maybe_verify_signature(request, data_id=str(merchant_order_id))

        payment_id, mo = await _resolve_payment_id_from_merchant_order(str(merchant_order_id))
        if not payment_id:
            print("merchant_order had no payments after retries. mo=", mo)
            return {"ok": True, "ignored": "merchant_order_no_payments_yet"}

    if not payment_id:
        return {"ok": True, "ignored": True}

    _maybe_verify_signature(request, data_id=str(payment_id))

    payment = await fetch_payment(str(payment_id))
    return await _process_payment(str(payment_id), payment, db)
