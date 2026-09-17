from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
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


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schemas = schema.get("components", {}).get("schemas", {}).values()
    for request_schema in schemas:
        upload_field = request_schema.get("properties", {}).get(
            "mulkiya_inspection_documents"
        )
        if upload_field:
            for variant in upload_field.get("anyOf", []):
                items = variant.get("items")
                if isinstance(items, dict) and items.get("type") == "string":
                    items["format"] = "binary"
                    items.pop("contentMediaType", None)

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


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
