"""
API Routes for Blackbird Search Engine

Defines all REST API endpoints.
"""

from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

router = APIRouter()


# Request/Response Models

class SearchRequest(BaseModel):
    """Search request body"""
    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")
    min_score: float = Field(default=0.0, ge=0.0, description="Minimum score")
    language: Optional[str] = Field(default=None, description="Filter by language")
    repo_id: Optional[str] = Field(default=None, description="Filter by repo")


class SearchResultItem(BaseModel):
    """A single search result"""
    doc_id: str
    repo_id: str
    path: str
    language: str
    score: float
    matched_ngrams: int
    has_symbol_match: bool
    snippet: str
    highlights: List[dict]


class SearchResponse(BaseModel):
    """Search response"""
    query: str
    total_results: int
    results: List[SearchResultItem]
    took_ms: float
    shards_queried: int


class IndexRepoRequest(BaseModel):
    """Request to index a repository"""
    path: str = Field(..., description="Path to repository")
    repo_id: Optional[str] = Field(default=None, description="Optional repo ID")


class IndexRepoResponse(BaseModel):
    """Response from indexing a repository"""
    repo_id: str
    documents_indexed: int
    documents_skipped: int
    duration_seconds: float
    errors: List[str]


class StatsResponse(BaseModel):
    """System statistics response"""
    num_shards: int
    total_documents: int
    total_ngrams: int
    shards: List[dict]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str


# Global services (set by main.py)
_search_service = None
_shard_manager = None
_crawler = None


def set_services(search_service, shard_manager, crawler):
    """Set global service references"""
    global _search_service, _shard_manager, _crawler
    _search_service = search_service
    _shard_manager = shard_manager
    _crawler = crawler


# Endpoints

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    
    Returns the service status and version.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0"
    )


@router.get("/search", response_model=SearchResponse, tags=["Search"])
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    min_score: float = Query(default=0.0, ge=0.0, description="Minimum score"),
    language: Optional[str] = Query(default=None, description="Filter by language"),
    repo_id: Optional[str] = Query(default=None, description="Filter by repo")
):
    """
    Search code across all indexed repositories.
    
    Uses ngram-based substring matching to find relevant code files.
    Results are ranked by relevance score.
    """
    if not _search_service:
        raise HTTPException(status_code=503, detail="Search service not initialized")
    
    try:
        response = _search_service.search(
            query=q,
            limit=limit,
            min_score=min_score,
            language=language,
            repo_id=repo_id
        )
        return response.to_dict()
    except Exception as e:
        logger.error("Search failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse, tags=["Search"])
async def search_post(request: SearchRequest):
    """
    Search code (POST version for complex queries).
    """
    return await search(
        q=request.query,
        limit=request.limit,
        min_score=request.min_score,
        language=request.language,
        repo_id=request.repo_id
    )


@router.post("/index/repo", response_model=IndexRepoResponse, tags=["Indexing"])
async def index_repository(
    request: IndexRepoRequest,
    background_tasks: BackgroundTasks
):
    """
    Index a repository from the local filesystem.
    
    Crawls the repository, extracts code files, and indexes them
    for search.
    """
    if not _crawler or not _shard_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")
    
    try:
        # Crawl the repository
        if path.is_dir() and (path / ".git").exists():
            result = _crawler.crawl_repo(str(path), repo_id=request.repo_id)
        else:
            result = _crawler.crawl_directory(str(path), repo_id=request.repo_id)
        
        # Index documents
        indexed = _shard_manager.index_documents(result.documents)
        
        return IndexRepoResponse(
            repo_id=result.repo_id,
            documents_indexed=indexed,
            documents_skipped=result.stats.skipped_files,
            duration_seconds=result.stats.duration_seconds,
            errors=result.stats.errors
        )
    except Exception as e:
        logger.error("Indexing failed", path=str(path), error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/index/repo/{repo_id}", tags=["Indexing"])
async def delete_repository(repo_id: str):
    """
    Delete all documents from a repository.
    
    Note: This is not yet fully implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Repository deletion not yet implemented"
    )


@router.get("/stats", response_model=StatsResponse, tags=["System"])
async def get_stats():
    """
    Get system statistics.
    
    Returns information about shards, document counts, and index size.
    """
    if not _shard_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    stats = _shard_manager.get_stats()
    return StatsResponse(
        num_shards=stats["num_shards"],
        total_documents=stats["total_documents"],
        total_ngrams=stats["total_ngrams"],
        shards=stats["shards"]
    )


@router.post("/admin/compact", tags=["Admin"])
async def trigger_compaction(
    force: bool = Query(default=False, description="Force compaction")
):
    """
    Trigger index compaction.
    
    Merges small index segments into larger ones for better performance.
    """
    if not _shard_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    try:
        _shard_manager.run_compaction(force=force)
        return {"status": "compaction_triggered"}
    except Exception as e:
        logger.error("Compaction failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/save", tags=["Admin"])
async def save_index():
    """
    Save index to disk.
    
    Persists all shard indices to disk.
    """
    if not _shard_manager:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    try:
        _shard_manager.save_all()
        return {"status": "saved"}
    except Exception as e:
        logger.error("Save failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
