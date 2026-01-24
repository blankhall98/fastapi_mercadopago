from fastapi import FastAPI
from app.core.config import settings
from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.mp_webhook import router as mp_webhook_router

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    def health():
        return {"status" : "ok", "env" : settings.app_env}
    
    # Include authentication routes
    app.include_router(auth_router)
    # Include billing routes
    app.include_router(billing_router)
    # Include Mercado Pago webhook routes
    app.include_router(mp_webhook_router)
    
    return app

app = create_app()