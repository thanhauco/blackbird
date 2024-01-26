"""
Caching Layer

Provides caching for embeddings, search results, and API responses.
"""

from typing import Any, Optional, Dict, Callable, TypeVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import json
import threading
import structlog

logger = structlog.get_logger()

T = TypeVar('T')


@dataclass
class CacheEntry:
    """A cached value with metadata"""
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    hits: int = 0
    size_bytes: int = 0


class LRUCache:
    """
    Least Recently Used (LRU) cache implementation.
    
    Thread-safe with configurable max size.
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600
    ):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of entries
            ttl_seconds: Time-to-live in seconds
        """
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: Dict[str, CacheEntry] = {}
        self.access_order: Dict[str, datetime] = {}
        self._lock = threading.Lock()
        
        # Stats
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            entry = self.cache[key]
            
            # Check expiration
            if entry.expires_at and datetime.now() > entry.expires_at:
                del self.cache[key]
                del self.access_order[key]
                self.misses += 1
                return None
            
            # Update access time
            self.access_order[key] = datetime.now()
            entry.hits += 1
            self.hits += 1
            
            return entry.value
    
    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ):
        """Set value in cache"""
        with self._lock:
            # Evict if at capacity
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_oldest()
            
            now = datetime.now()
            ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else self.ttl
            
            self.cache[key] = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + ttl,
                size_bytes=self._estimate_size(value)
            )
            self.access_order[key] = now
    
    def _evict_oldest(self):
        """Evict least recently used entry"""
        if not self.access_order:
            return
        
        oldest_key = min(self.access_order, key=self.access_order.get)
        del self.cache[oldest_key]
        del self.access_order[oldest_key]
    
    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of value"""
        try:
            return len(json.dumps(value, default=str))
        except:
            return 0
    
    def invalidate(self, key: str):
        """Remove entry from cache"""
        with self._lock:
            if key in self.cache:
                del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
    
    def clear(self):
        """Clear all entries"""
        with self._lock:
            self.cache.clear()
            self.access_order.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_size = sum(e.size_bytes for e in self.cache.values())
        hit_rate = self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0
        
        return {
            "entries": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "total_size_bytes": total_size
        }


class EmbeddingCache:
    """
    Specialized cache for embeddings.
    
    Uses content hashing for deduplication.
    """
    
    def __init__(self, max_size: int = 10000):
        self.cache = LRUCache(max_size=max_size, ttl_seconds=86400)  # 24h TTL
    
    def _content_hash(self, content: str) -> str:
        """Hash content for cache key"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get_embedding(self, content: str) -> Optional[Any]:
        """Get cached embedding for content"""
        key = f"emb:{self._content_hash(content)}"
        return self.cache.get(key)
    
    def set_embedding(self, content: str, embedding: Any):
        """Cache embedding for content"""
        key = f"emb:{self._content_hash(content)}"
        self.cache.set(key, embedding)
    
    def get_or_compute(
        self,
        content: str,
        compute_fn: Callable[[str], Any]
    ) -> Any:
        """Get cached or compute embedding"""
        cached = self.get_embedding(content)
        if cached is not None:
            return cached
        
        embedding = compute_fn(content)
        self.set_embedding(content, embedding)
        return embedding


class SearchCache:
    """
    Cache for search results.
    """
    
    def __init__(self, max_size: int = 5000, ttl_seconds: int = 300):
        self.cache = LRUCache(max_size=max_size, ttl_seconds=ttl_seconds)
    
    def _query_hash(self, query: str, filters: Dict[str, Any]) -> str:
        """Create cache key from query and filters"""
        key_data = f"{query}:{json.dumps(filters, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get_results(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Get cached search results"""
        key = self._query_hash(query, filters or {})
        return self.cache.get(key)
    
    def set_results(
        self,
        query: str,
        results: Any,
        filters: Optional[Dict[str, Any]] = None
    ):
        """Cache search results"""
        key = self._query_hash(query, filters or {})
        self.cache.set(key, results)
    
    def invalidate_for_doc(self, doc_id: str):
        """Invalidate cache entries containing a document"""
        # For simplicity, clear all on document change
        # A more sophisticated implementation would track doc -> query mappings
        self.cache.clear()


def cached(
    cache: LRUCache,
    key_fn: Optional[Callable[..., str]] = None,
    ttl_seconds: Optional[int] = None
):
    """
    Decorator for caching function results.
    
    Args:
        cache: Cache instance to use
        key_fn: Function to generate cache key from args
        ttl_seconds: Override TTL for this function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Generate cache key
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                key = f"{func.__name__}:{hash((args, tuple(sorted(kwargs.items()))))}"
            
            # Check cache
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
            
            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(key, result, ttl_seconds)
            
            return result
        
        return wrapper
    return decorator


class CacheManager:
    """
    Manages multiple caches for the application.
    """
    
    def __init__(self):
        self.embedding_cache = EmbeddingCache(max_size=10000)
        self.search_cache = SearchCache(max_size=5000)
        self.general_cache = LRUCache(max_size=1000)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stats for all caches"""
        return {
            "embedding": self.embedding_cache.cache.get_stats(),
            "search": self.search_cache.cache.get_stats(),
            "general": self.general_cache.get_stats()
        }
    
    def clear_all(self):
        """Clear all caches"""
        self.embedding_cache.cache.clear()
        self.search_cache.cache.clear()
        self.general_cache.clear()
        logger.info("All caches cleared")
    
    def on_document_change(self, doc_id: str):
        """Handle document change - invalidate relevant caches"""
        self.search_cache.invalidate_for_doc(doc_id)
