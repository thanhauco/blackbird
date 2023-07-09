"""
Blackbird API Module

FastAPI-based REST API for search and indexing.
"""

from .main import app, create_app
from .search import SearchService
from .routes import router

__all__ = [
    "app",
    "create_app",
    "SearchService",
    "router"
]
