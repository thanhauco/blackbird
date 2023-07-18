"""
Main FastAPI Application for Blackbird Search Engine
"""

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog

from .routes import router, set_services
from .search import SearchService
from ..shard.manager import ShardManager
from ..crawler.git_crawler import GitCrawler
from ..config import get_config

logger = structlog.get_logger()

# Global instances
shard_manager: ShardManager = None
search_service: SearchService = None
crawler: GitCrawler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    
    Initializes services on startup and cleans up on shutdown.
    """
    global shard_manager, search_service, crawler
    
    config = get_config()
    
    # Initialize services
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
    
    # Set services in routes
    set_services(search_service, shard_manager, crawler)
    
    # Try to load existing index
    try:
        shard_manager.load_all()
        logger.info("Loaded existing index")
    except Exception as e:
        logger.info("No existing index found, starting fresh", error=str(e))
    
    logger.info("Blackbird services initialized")
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down Blackbird services...")
    shard_manager.shutdown()
    logger.info("Blackbird services shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """
    config = get_config()
    
    app = FastAPI(
        title="Blackbird Search Engine",
        description="""
        A high-performance code search engine inspired by GitHub's Blackbird.
        
        ## Features
        
        - **Ngram-based search**: Fast substring matching using trigram indices
        - **Symbol extraction**: Prioritizes matches in function/class names
        - **Distributed sharding**: Parallel indexing and search
        - **Delta crawling**: Efficient repository updates
        
        ## Quick Start
        
        1. Index a repository: `POST /index/repo`
        2. Search code: `GET /search?q=your+query`
        """,
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # API routes
    app.include_router(router, prefix="/api")
    
    # Also mount routes at root for convenience
    app.include_router(router)
    
    # Static files for web UI
    web_dir = Path(__file__).parent.parent / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")
        
        @app.get("/", include_in_schema=False)
        async def serve_ui():
            """Serve the web UI"""
            return FileResponse(str(web_dir / "index.html"))
    
    return app


# Create the default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    config = get_config()
    
    uvicorn.run(
        "blackbird.api.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=True
    )
