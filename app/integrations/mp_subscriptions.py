import httpx
from app.core.config import settings

MP_API = "https://api.mercadopago.com"

async def mp_create_preapproval(payload: dict) -> tuple[int, dict]:
    """
    Creates a subscription (preapproval) and returns (status_code, json).
    Docs: POST /preapproval
    """
    headers = {"Authorization": f"Bearer {settings.mp_access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{MP_API}/preapproval", json=payload, headers=headers)
    return r.status_code, (r.json() if r.content else {})

async def mp_get_preapproval(preapproval_id: str) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {settings.mp_access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{MP_API}/preapproval/{preapproval_id}", headers=headers)
    return r.status_code, (r.json() if r.content else {})

async def mp_update_preapproval(preapproval_id: str, payload: dict) -> tuple[int, dict]:
    """
    Updates a subscription (preapproval) and returns (status_code, json).
    Docs: PUT /preapproval/{id}
    """
    headers = {"Authorization": f"Bearer {settings.mp_access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.put(f"{MP_API}/preapproval/{preapproval_id}", json=payload, headers=headers)
    return r.status_code, (r.json() if r.content else {})
