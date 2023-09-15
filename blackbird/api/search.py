"""
Search Service for Blackbird Search Engine

Provides high-level search functionality with result enrichment.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import structlog

from ..core.index import SearchResult
from ..core.ngram import NgramTokenizer
from ..shard.manager import ShardManager
from ..ml.embeddings import SemanticSearchEngine
from ..ml.hybrid import HybridSearchEngine, SearchMode
from ..config import get_config

logger = structlog.get_logger()


@dataclass
class EnrichedResult:
    """
    Search result with additional context and metadata.
    """
    doc_id: str
    repo_id: str
    path: str
    language: str
    score: float
    matched_ngrams: int
    has_symbol_match: bool
    snippet: str = ""
    highlights: List[Dict[str, int]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "repo_id": self.repo_id,
            "path": self.path,
            "language": self.language,
            "score": self.score,
            "matched_ngrams": self.matched_ngrams,
            "has_symbol_match": self.has_symbol_match,
            "snippet": self.snippet,
            "highlights": self.highlights
        }


@dataclass
class SearchResponse:
    """
    Response from a search query.
    """
    query: str
    total_results: int
    results: List[EnrichedResult]
    took_ms: float
    shards_queried: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total_results": self.total_results,
            "results": [r.to_dict() for r in self.results],
            "took_ms": self.took_ms,
            "shards_queried": self.shards_queried
        }


class SearchService:
    """
    High-level search service.
    
    Wraps the shard manager to provide search with result
    enrichment, snippet generation, and highlighting.
    """
    
    def __init__(
        self,
        shard_manager: ShardManager,
        snippet_length: int = 200
    ):
        """
        Initialize the search service.
        
        Args:
            shard_manager: Manager for distributed shards
            snippet_length: Maximum snippet length
        """
        self.shard_manager = shard_manager
        self.snippet_length = snippet_length
        self.tokenizer = NgramTokenizer()
        
        # Initialize semantic search
        self.semantic_engine = SemanticSearchEngine()
        
        # Initialize hybrid search
        # Wrap shard manager to look like an index
        class ShardManagerAdapter:
            def __init__(self, manager):
                self.manager = manager
            def search(self, query, limit, min_score):
                return self.manager.search(query, limit, min_score)
        
        self.hybrid_engine = HybridSearchEngine(
            ngram_index=ShardManagerAdapter(shard_manager),
            semantic_engine=self.semantic_engine
        )
        
        logger.info("Search service initialized")
    
    def search(
        self,
        query: str,
        limit: int = 20,
        min_score: float = 0.0,
        language: Optional[str] = None,
        repo_id: Optional[str] = None
    ) -> SearchResponse:
        """
        Execute a search query.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            min_score: Minimum score threshold
            language: Filter by language (optional)
            repo_id: Filter by repository (optional)
            
        Returns:
            SearchResponse with enriched results
        """
        start_time = datetime.utcnow()
        
        # Execute hybrid search
        # Determine mode based on config or query analysis
        mode = SearchMode.HYBRID
        
        raw_results = self.hybrid_engine.search(
            query=query,
            mode=mode,
            limit=limit * 2,
            min_score=min_score,
            language=language
        )
        
        # Filter results
        if language:
            raw_results = [
                r for r in raw_results
                if r.language.lower() == language.lower()
            ]
        
        if repo_id:
            raw_results = [
                r for r in raw_results
                if r.repo_id == repo_id
            ]
        
        # Limit after filtering
        raw_results = raw_results[:limit]
        
        # Enrich results
        enriched = [
            self._enrich_result(r, query)
            for r in raw_results
        ]
        
        took_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        response = SearchResponse(
            query=query,
            total_results=len(enriched),
            results=enriched,
            took_ms=took_ms,
            shards_queried=self.shard_manager.num_shards
        )
        
        logger.info(
            "Search completed",
            query=query,
            results=len(enriched),
            took_ms=f"{took_ms:.2f}"
        )
        
        return response
    
    def _enrich_result(
        self,
        result: SearchResult,
        query: str
    ) -> EnrichedResult:
        """
        Enrich a search result with snippets and highlights.
        """
        return EnrichedResult(
            doc_id=result.doc_id,
            repo_id=result.repo_id,
            path=result.path,
            language=result.language,
            score=result.score,
            matched_ngrams=result.matched_ngrams,
            has_symbol_match=result.has_symbol_match,
            snippet=result.snippet,
            highlights=[
                {"start": h[0], "end": h[1]}
                for h in result.highlights
            ]
        )
    
    def get_suggestions(
        self,
        prefix: str,
        limit: int = 10
    ) -> List[str]:
        """
        Get search suggestions based on prefix.
        
        This is a placeholder for autocomplete functionality.
        """
        # TODO: Implement prefix-based suggestions
        return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search service statistics"""
        return {
            "shard_stats": self.shard_manager.get_stats()
        }
