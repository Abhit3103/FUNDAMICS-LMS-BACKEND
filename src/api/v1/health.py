from fastapi import APIRouter, status
from sqlalchemy import text
from src.config import settings
from src.database import engine

router = APIRouter(tags=["Health & Status"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Liveness probe: confirms API process is running."""
    return {"status": "ok", "app": settings.PROJECT_NAME}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe():
    """Readiness probe: validates database connectivity."""
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unavailable: {str(e)}"
        return {
            "status": "not_ready",
            "database": db_status,
            "version": settings.VERSION,
        }

    return {
        "status": "ready",
        "database": db_status,
        "version": settings.VERSION,
    }


@router.get("/version", status_code=status.HTTP_200_OK)
async def version_info():
    """Returns application version and environment metadata."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.APP_ENV,
        "timezone": settings.TIMEZONE,
    }
