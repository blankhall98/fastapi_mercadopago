from fastapi import FastAPI
from app.core.config import settings
from app.api.auth import router as auth_router

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    def health():
        return {"status" : "ok", "env" : settings.app_env}
    
    # Include authentication routes
    app.include_router(auth_router)
    
    return app

app = create_app()