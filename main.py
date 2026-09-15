from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.api_router import api_router
from app.config.settings import settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager:
    - Runs on startup: Initializes database tables & seeds Super Admin account from .env
    - Runs on shutdown: Cleanly tears down resources
    """
    print(f"Starting {settings.APP_NAME}...")
    init_db()
    yield
    print(f"Shutting down {settings.APP_NAME}...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Alsabouh Web App Backend - High-performance modular API for Fleet, Drivers, and Operations.",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Register API routes
app.include_router(api_router)


@app.get("/", tags=["Health"])
def health_check():
    """Root health check endpoint."""
    return {
        "app_name": settings.APP_NAME,
        "status": "healthy",
        "version": "1.0.0",
        "docs_url": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main.py:app", host="0.0.0.0", port=8000, reload=True)
