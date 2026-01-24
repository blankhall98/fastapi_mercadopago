import hmac
import hashlib
from typing import Optional

def _parse_x_signature(x_signature: str) -> tuple[Optional[str], Optional[str]]:
    """
    x-signature looks like: "ts=1700000000,v1=abcdef..."
    """
    ts = None
    v1 = None
    for part in x_signature.split(","):
        k, _, v = part.strip().partition("=")
        if k == "ts":
            ts = v
        elif k == "v1":
            v1 = v
    return ts, v1

def verify_mp_signature(*, secret: str, x_signature: str, x_request_id: str, data_id: str) -> bool:
    """
    Manifest used by Mercado Pago examples seen in the wild:
    id:{data_id};request-id:{x_request_id};ts:{ts};
    Then HMAC SHA256 with secret, hex digest, compared to v1.
    """
    ts, v1 = _parse_x_signature(x_signature)
    if not ts or not v1:
        return False
    
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    digest = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, v1)
    