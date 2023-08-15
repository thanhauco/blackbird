#!/usr/bin/env python3
"""
Blackbird Search Engine - Server Runner

Run this script from the project root to start the server.
"""

import sys
import os

# Add project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

# Now we can import our modules
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

# Import our modules
from blackbird.shard.manager import ShardManager
from blackbird.crawler.git_crawler import GitCrawler
from blackbird.api.search import SearchService
from blackbird.api.routes import router, set_services
from blackbird.config import get_config

# Global instances
shard_manager = None
search_service = None
crawler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    global shard_manager, search_service, crawler
    
    config = get_config()
    
    logger.info("Initializing Blackbird services...")
    
    shard_manager = ShardManager(
        num_shards=config.NUM_SHARDS,
        index_path=config.INDEX_PATH,
        ngram_size=config.NGRAM_SIZE
    )
    
    search_service = SearchService(shard_manager)
    
    crawler = GitCrawler(
        max_file_size_mb=config.MAX_FILE_SIZE_MB,
        supported_extensions=config.SUPPORTED_EXTENSIONS,
        excluded_dirs=config.EXCLUDED_DIRS
    )
    
    set_services(search_service, shard_manager, crawler)
    
    try:
        shard_manager.load_all()
        logger.info("Loaded existing index")
    except Exception as e:
        logger.info("No existing index found, starting fresh")
    
    logger.info("Blackbird services initialized")
    
    yield
    
    logger.info("Shutting down Blackbird services...")
    shard_manager.shutdown()
    logger.info("Blackbird services shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    config = get_config()
    
    app = FastAPI(
        title="Blackbird Search Engine",
        description="A high-performance code search engine inspired by GitHub's Blackbird",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # API routes
    app.include_router(router, prefix="/api")
    app.include_router(router)
    
    # Static files for web UI
    web_dir = Path(__file__).parent / "blackbird" / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")
        
        @app.get("/", include_in_schema=False)
        async def serve_ui():
            return FileResponse(str(web_dir / "index.html"))
    
    return app


# Create app
app = create_app()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  BLACKBIRD SEARCH ENGINE")
    print("  A code search engine inspired by GitHub's Blackbird")
    print("="*60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
