import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import router
from .objections import router as objections_router

app = FastAPI(title="Smart Glosas AI", version="0.5.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins,
                   allow_headers=["Authorization", "Content-Type", "X-Tenant-Id"],
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_credentials=True)

@app.get("/health")
def health():
    return {"status": "ok", "service": "smart-glosas-ai", "version": "0.5.0"}

app.include_router(router)
app.include_router(objections_router)
