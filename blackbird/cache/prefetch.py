"""
Cache Warming and Prefetching

Optimizes cache performance through intelligent prefetching.
"""

from typing import List, Dict, Set, Optional, Callable
from dataclasses import dataclass
from collections import defaultdict
import threading
import time


@dataclass
class AccessPattern:
    """Records access patterns for prefetching"""
    key: str
    timestamp: float
    source: str = ""


class CacheWarmer:
    """Warms cache with frequently accessed items"""
    
    def __init__(self, cache, compute_fn: Callable):
        self.cache = cache
        self.compute_fn = compute_fn
        self.access_history: List[AccessPattern] = []
        self.popular_keys: Set[str] = set()
    
    def record_access(self, key: str, source: str = ""):
        """Record a cache access"""
        self.access_history.append(AccessPattern(
            key=key,
            timestamp=time.time(),
            source=source
        ))
        
        # Trim old history
        if len(self.access_history) > 10000:
            self.access_history = self.access_history[-5000:]
    
    def analyze_patterns(self) -> Dict[str, int]:
        """Analyze access patterns"""
        counts = defaultdict(int)
        for access in self.access_history:
            counts[access.key] += 1
        return dict(counts)
    
    def get_popular_keys(self, min_count: int = 5) -> List[str]:
        """Get frequently accessed keys"""
        counts = self.analyze_patterns()
        return [k for k, c in counts.items() if c >= min_count]
    
    def warm(self, keys: Optional[List[str]] = None):
        """Warm cache with specified or popular keys"""
        keys_to_warm = keys or self.get_popular_keys()
        
        for key in keys_to_warm:
            if self.cache.get(key) is None:
                try:
                    value = self.compute_fn(key)
                    self.cache.set(key, value)
                except Exception:
                    pass  # Skip failed computations


class Prefetcher:
    """Prefetches related items based on access patterns"""
    
    def __init__(self, cache, fetch_fn: Callable):
        self.cache = cache
        self.fetch_fn = fetch_fn
        self.associations: Dict[str, Set[str]] = defaultdict(set)
        self._prefetch_thread: Optional[threading.Thread] = None
    
    def record_co_access(self, key1: str, key2: str):
        """Record that two keys were accessed together"""
        self.associations[key1].add(key2)
        self.associations[key2].add(key1)
    
    def get_related(self, key: str) -> List[str]:
        """Get keys related to the given key"""
        return list(self.associations.get(key, set()))
    
    def prefetch_async(self, key: str):
        """Prefetch related keys asynchronously"""
        related = self.get_related(key)
        
        if not related:
            return
        
        def prefetch():
            for related_key in related[:5]:  # Limit prefetch
                if self.cache.get(related_key) is None:
                    try:
                        value = self.fetch_fn(related_key)
                        self.cache.set(related_key, value)
                    except Exception:
                        pass
        
        self._prefetch_thread = threading.Thread(target=prefetch)
        self._prefetch_thread.start()


class TieredCache:
    """Multi-tiered cache with different TTLs"""
    
    def __init__(self, hot_size: int = 100, warm_size: int = 1000, cold_size: int = 10000):
        from .cache import LRUCache
        
        self.hot = LRUCache(max_size=hot_size, ttl_seconds=60)
        self.warm = LRUCache(max_size=warm_size, ttl_seconds=300)
        self.cold = LRUCache(max_size=cold_size, ttl_seconds=3600)
    
    def get(self, key: str):
        """Get from tiered cache"""
        # Check hot tier first
        value = self.hot.get(key)
        if value is not None:
            return value
        
        # Check warm tier
        value = self.warm.get(key)
        if value is not None:
            # Promote to hot
            self.hot.set(key, value)
            return value
        
        # Check cold tier
        value = self.cold.get(key)
        if value is not None:
            # Promote to warm
            self.warm.set(key, value)
            return value
        
        return None
    
    def set(self, key: str, value, hot: bool = False):
        """Set in appropriate tier"""
        if hot:
            self.hot.set(key, value)
        else:
            self.cold.set(key, value)
    
    def get_stats(self) -> Dict:
        """Get stats for all tiers"""
        return {
            "hot": self.hot.get_stats(),
            "warm": self.warm.get_stats(),
            "cold": self.cold.get_stats()
        }
