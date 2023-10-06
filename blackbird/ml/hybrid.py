"""
Hybrid Search Engine

Combines ngram-based search with semantic vector search
for best-of-both-worlds code search.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..core.index import InvertedIndex, SearchResult
from .embeddings import SemanticSearchEngine, SemanticSearchResult

logger = structlog.get_logger()


class SearchMode(Enum):
    """Search mode selection"""
    NGRAM = "ngram"           # Traditional ngram search
    SEMANTIC = "semantic"      # Neural semantic search
    HYBRID = "hybrid"          # Combined search


@dataclass
class HybridSearchResult:
    """
    Result from hybrid search combining multiple signals.
    """
    doc_id: str
    repo_id: str
    path: str
    language: str
    
    # Scores from different sources
    ngram_score: float = 0.0
    semantic_score: float = 0.0
    combined_score: float = 0.0
    
    # Match details
    matched_ngrams: int = 0
    has_symbol_match: bool = False
    snippet: str = ""
    
    # Ranking metadata
    rank_features: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "repo_id": self.repo_id,
            "path": self.path,
            "language": self.language,
            "ngram_score": self.ngram_score,
            "semantic_score": self.semantic_score,
            "combined_score": self.combined_score,
            "matched_ngrams": self.matched_ngrams,
            "has_symbol_match": self.has_symbol_match,
            "snippet": self.snippet
        }


class HybridSearchEngine:
    """
    Hybrid search engine combining ngram and semantic search.
    
    Uses reciprocal rank fusion (RRF) or weighted combination
    to merge results from both search methods.
    """
    
    def __init__(
        self,
        ngram_index: InvertedIndex,
        semantic_engine: Optional[SemanticSearchEngine] = None,
        ngram_weight: float = 0.6,
        semantic_weight: float = 0.4,
        rrf_k: int = 60
    ):
        """
        Initialize hybrid search engine.
        
        Args:
            ngram_index: Traditional ngram inverted index
            semantic_engine: Neural semantic search engine
            ngram_weight: Weight for ngram scores (0-1)
            semantic_weight: Weight for semantic scores (0-1)
            rrf_k: RRF constant (higher = less top-heavy)
        """
        self.ngram_index = ngram_index
        self.semantic_engine = semantic_engine
        self.ngram_weight = ngram_weight
        self.semantic_weight = semantic_weight
        self.rrf_k = rrf_k
        
        logger.info(
            "Hybrid search engine initialized",
            ngram_weight=ngram_weight,
            semantic_weight=semantic_weight
        )
    
    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.HYBRID,
        limit: int = 20,
        min_score: float = 0.0,
        language: Optional[str] = None
    ) -> List[HybridSearchResult]:
        """
        Perform hybrid search.
        
        Args:
            query: Search query
            mode: Search mode (ngram, semantic, or hybrid)
            limit: Maximum results
            min_score: Minimum score threshold
            language: Optional language filter
            
        Returns:
            List of ranked search results
        """
        if mode == SearchMode.NGRAM:
            return self._ngram_search(query, limit, min_score)
        elif mode == SearchMode.SEMANTIC:
            return self._semantic_search(query, limit, min_score)
        else:
            return self._hybrid_search(query, limit, min_score, language)
    
    def _ngram_search(
        self,
        query: str,
        limit: int,
        min_score: float
    ) -> List[HybridSearchResult]:
        """Perform ngram-only search"""
        results = self.ngram_index.search(query, limit, min_score)
        
        return [
            HybridSearchResult(
                doc_id=r.doc_id,
                repo_id=r.repo_id,
                path=r.path,
                language=r.language,
                ngram_score=r.score,
                combined_score=r.score,
                matched_ngrams=r.matched_ngrams,
                has_symbol_match=r.has_symbol_match,
                snippet=r.snippet
            )
            for r in results
        ]
    
    def _semantic_search(
        self,
        query: str,
        limit: int,
        min_score: float
    ) -> List[HybridSearchResult]:
        """Perform semantic-only search"""
        if not self.semantic_engine:
            return []
        
        results = self.semantic_engine.search(query, limit, min_score)
        
        return [
            HybridSearchResult(
                doc_id=r.doc_id,
                repo_id=r.metadata.get("repo_id", ""),
                path=r.metadata.get("path", ""),
                language=r.metadata.get("language", ""),
                semantic_score=r.score,
                combined_score=r.score
            )
            for r in results
        ]
    
    def _hybrid_search(
        self,
        query: str,
        limit: int,
        min_score: float,
        language: Optional[str] = None
    ) -> List[HybridSearchResult]:
        """
        Perform hybrid search using RRF fusion.
        
        Reciprocal Rank Fusion (RRF) formula:
        score(d) = sum(1 / (k + rank_i(d))) for each ranking
        """
        # Get results from both engines
        ngram_results = self.ngram_index.search(query, limit * 2, 0)
        
        semantic_results = []
        if self.semantic_engine:
            semantic_results = self.semantic_engine.search(query, limit * 2, 0)
        
        # Build document maps
        doc_map: Dict[str, HybridSearchResult] = {}
        
        # Process ngram results
        for rank, r in enumerate(ngram_results):
            if r.doc_id not in doc_map:
                doc_map[r.doc_id] = HybridSearchResult(
                    doc_id=r.doc_id,
                    repo_id=r.repo_id,
                    path=r.path,
                    language=r.language,
                    matched_ngrams=r.matched_ngrams,
                    has_symbol_match=r.has_symbol_match,
                    snippet=r.snippet
                )
            
            doc_map[r.doc_id].ngram_score = r.score
            doc_map[r.doc_id].rank_features["ngram_rank"] = rank + 1
        
        # Process semantic results
        for rank, r in enumerate(semantic_results):
            if r.doc_id not in doc_map:
                doc_map[r.doc_id] = HybridSearchResult(
                    doc_id=r.doc_id,
                    repo_id=r.metadata.get("repo_id", ""),
                    path=r.metadata.get("path", ""),
                    language=r.metadata.get("language", ""),
                )
            
            doc_map[r.doc_id].semantic_score = r.score
            doc_map[r.doc_id].rank_features["semantic_rank"] = rank + 1
        
        # Calculate RRF scores
        for doc_id, result in doc_map.items():
            rrf_score = 0.0
            
            if "ngram_rank" in result.rank_features:
                rrf_score += self.ngram_weight / (
                    self.rrf_k + result.rank_features["ngram_rank"]
                )
            
            if "semantic_rank" in result.rank_features:
                rrf_score += self.semantic_weight / (
                    self.rrf_k + result.rank_features["semantic_rank"]
                )
            
            result.combined_score = rrf_score
        
        # Sort by combined score
        results = list(doc_map.values())
        results.sort(key=lambda x: x.combined_score, reverse=True)
        
        # Filter by language if specified
        if language:
            results = [r for r in results if r.language.lower() == language.lower()]
        
        # Filter by minimum score
        results = [r for r in results if r.combined_score >= min_score]
        
        logger.info(
            "Hybrid search completed",
            query=query,
            ngram_results=len(ngram_results),
            semantic_results=len(semantic_results),
            merged_results=len(results)
        )
        
        return results[:limit]
    
    def explain_ranking(
        self,
        result: HybridSearchResult
    ) -> Dict[str, Any]:
        """
        Explain why a result was ranked at its position.
        """
        return {
            "doc_id": result.doc_id,
            "scores": {
                "ngram": result.ngram_score,
                "semantic": result.semantic_score,
                "combined": result.combined_score
            },
            "rank_features": result.rank_features,
            "weights": {
                "ngram": self.ngram_weight,
                "semantic": self.semantic_weight
            },
            "signals": {
                "matched_ngrams": result.matched_ngrams,
                "has_symbol_match": result.has_symbol_match
            }
        }


class AdaptiveSearchEngine:
    """
    Adaptive search engine that learns optimal weights
    from user feedback and click-through data.
    """
    
    def __init__(
        self,
        hybrid_engine: HybridSearchEngine,
        learning_rate: float = 0.01
    ):
        self.hybrid_engine = hybrid_engine
        self.learning_rate = learning_rate
        
        # Click-through tracking
        self.impressions: Dict[str, int] = {}
        self.clicks: Dict[str, int] = {}
        
        # Query-specific weights
        self.query_weights: Dict[str, Tuple[float, float]] = {}
    
    def record_impression(self, query: str, doc_ids: List[str]):
        """Record search impressions"""
        for doc_id in doc_ids:
            key = f"{query}:{doc_id}"
            self.impressions[key] = self.impressions.get(key, 0) + 1
    
    def record_click(self, query: str, doc_id: str):
        """Record a click on a search result"""
        key = f"{query}:{doc_id}"
        self.clicks[key] = self.clicks.get(key, 0) + 1
        
        # Update weights based on which score type was higher
        # This is a simplified version of online learning
        self._update_weights(query, doc_id)
    
    def _update_weights(self, query: str, doc_id: str):
        """Update weights based on click feedback"""
        # In a real implementation, this would use gradient descent
        # on a learning-to-rank model
        pass
    
    def get_ctr(self, query: str, doc_id: str) -> float:
        """Get click-through rate for a query-document pair"""
        key = f"{query}:{doc_id}"
        impressions = self.impressions.get(key, 0)
        clicks = self.clicks.get(key, 0)
        
        if impressions == 0:
            return 0.0
        
        return clicks / impressions
