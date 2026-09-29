"""
Convenience entrypoint allowing 'uvicorn main:app --reload' from repository root.
The core FastAPI application instance is implemented in src/main.py.
"""
from src.main import app

__all__ = ["app"]
