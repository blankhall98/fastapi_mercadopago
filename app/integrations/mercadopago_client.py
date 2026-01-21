import mercadopago
from app.core.config import settings

def mp_sdk() -> mercadopago.SDK:
    if not settings.mp_access_token:
        raise ValueError("Mercado Pago access token is not set in configuration.")
    return mercadopago.SDK(settings.mp_access_token)