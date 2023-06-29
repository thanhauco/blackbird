"""
Shard Manager for Blackbird Search Engine

Manages distributed index shards for parallel indexing and search.
"""

import os
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import structlog

from ..core.index import InvertedIndex, SearchResult
from ..core.document import CodeDocument
from ..core.compaction import CompactionEngine, DelayedCompactionEngine
from ..kafka.consumer import ShardConsumer
from ..kafka.producer import DocumentEvent
from .partition import PartitionAssigner, ShardRouter
from ..config import get_config

logger = structlog.get_logger()


@dataclass
class ShardStats:
    """Statistics for a shard"""
    shard_id: int
    document_count: int = 0
    ngram_count: int = 0
    index_size_bytes: int = 0
    segment_count: int = 0
    pending_messages: int = 0


class Shard:
    """
    A single index shard.
    
    Each shard maintains its own inverted index and handles
    indexing/search for its assigned documents.
    """
    
    def __init__(
        self,
        shard_id: int,
        index_path: Path,
        ngram_size: int = 3,
        enable_compaction: bool = True
    ):
        """
        Initialize the shard.
        
        Args:
            shard_id: Unique shard identifier
            index_path: Base path for index storage
            ngram_size: Size of ngrams for indexing
            enable_compaction: Enable automatic compaction
        """
        self.shard_id = shard_id
        self.index_path = index_path / f"shard_{shard_id}"
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        # Create index
        self.index = InvertedIndex(
            ngram_size=ngram_size,
            index_path=self.index_path / "index.idx"
        )
        
        # Create compaction engine
        if enable_compaction:
            self.compaction = DelayedCompactionEngine(
                segment_dir=self.index_path / "segments"
            )
        else:
            self.compaction = None
        
        # Consumer for this shard's partition
        self.consumer: Optional[ShardConsumer] = None
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        # Statistics
        self._docs_indexed = 0
        self._docs_deleted = 0
        
        logger.info(
            "Shard initialized",
            shard_id=shard_id,
            path=str(self.index_path)
        )
    
    def index_document(self, document: CodeDocument) -> bool:
        """
        Index a document.
        
        Returns:
            True if document was indexed (not duplicate)
        """
        with self._lock:
            success = self.index.add_document(document)
            if success:
                self._docs_indexed += 1
            return success
    
    def index_documents(self, documents: List[CodeDocument]) -> int:
        """
        Index multiple documents.
        
        Returns:
            Number of documents indexed
        """
        count = 0
        for doc in documents:
            if self.index_document(doc):
                count += 1
        return count
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from the index.
        
        Returns:
            True if document was found and deleted
        """
        with self._lock:
            success = self.index.remove_document(doc_id)
            if success:
                self._docs_deleted += 1
                if self.compaction:
                    self.compaction.mark_deleted(doc_id)
            return success
    
    def search(
        self,
        query: str,
        limit: int = 20,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search this shard.
        
        Returns:
            List of search results from this shard
        """
        with self._lock:
            return self.index.search(query, limit, min_score)
    
    def get_stats(self) -> ShardStats:
        """Get shard statistics"""
        with self._lock:
            index_stats = self.index.get_stats()
            
            return ShardStats(
                shard_id=self.shard_id,
                document_count=index_stats["document_count"],
                ngram_count=index_stats["ngram_count"],
                index_size_bytes=0,  # TODO: Calculate actual size
                segment_count=len(self.compaction.get_all_segments()) if self.compaction else 1,
                pending_messages=self.consumer.get_lag() if self.consumer else 0
            )
    
    def run_compaction(self, force: bool = False):
        """Run compaction if needed"""
        if self.compaction:
            self.compaction.compact(force=force)
    
    def save(self):
        """Persist the index to disk"""
        with self._lock:
            self.index.save()
            logger.info("Shard saved", shard_id=self.shard_id)
    
    def load(self):
        """Load index from disk"""
        with self._lock:
            index_file = self.index_path / "index.idx"
            if index_file.exists():
                self.index = InvertedIndex.load(index_file)
                logger.info("Shard loaded", shard_id=self.shard_id)


class ShardManager:
    """
    Manages all index shards.
    
    Coordinates indexing, search, and maintenance across shards.
    """
    
    def __init__(
        self,
        num_shards: int = 8,
        index_path: Optional[Path] = None,
        ngram_size: int = 3
    ):
        """
        Initialize the shard manager.
        
        Args:
            num_shards: Number of shards to create
            index_path: Base path for index storage
            ngram_size: Size of ngrams for indexing
        """
        config = get_config()
        
        self.num_shards = num_shards or config.NUM_SHARDS
        self.index_path = Path(index_path or config.INDEX_PATH)
        self.ngram_size = ngram_size
        
        # Create shards
        self.shards: Dict[int, Shard] = {}
        for i in range(self.num_shards):
            self.shards[i] = Shard(
                shard_id=i,
                index_path=self.index_path,
                ngram_size=ngram_size
            )
        
        # Router for partition assignment
        self.router = ShardRouter(num_shards)
        
        # Thread pool for parallel operations
        self._executor = ThreadPoolExecutor(max_workers=num_shards)
        
        # Bulk ingest mode
        self._bulk_mode = False
        
        logger.info(
            "Shard manager initialized",
            shards=num_shards,
            path=str(self.index_path)
        )
    
    def get_shard(self, shard_id: int) -> Shard:
        """Get a shard by ID"""
        return self.shards[shard_id]
    
    def get_shard_for_document(self, doc_id: str) -> Shard:
        """Get the shard responsible for a document"""
        shard_id = self.router.route_document(doc_id)
        return self.shards[shard_id]
    
    def index_document(self, document: CodeDocument) -> bool:
        """
        Index a document to the appropriate shard.
        
        Returns:
            True if document was indexed
        """
        shard = self.get_shard_for_document(document.id)
        return shard.index_document(document)
    
    def index_documents(self, documents: List[CodeDocument]) -> int:
        """
        Index multiple documents, distributing to appropriate shards.
        
        Returns:
            Total number of documents indexed
        """
        # Group documents by shard
        by_shard: Dict[int, List[CodeDocument]] = {}
        for doc in documents:
            shard_id = self.router.route_document(doc.id)
            if shard_id not in by_shard:
                by_shard[shard_id] = []
            by_shard[shard_id].append(doc)
        
        # Index in parallel
        total = 0
        futures = []
        for shard_id, docs in by_shard.items():
            future = self._executor.submit(
                self.shards[shard_id].index_documents, docs
            )
            futures.append(future)
        
        for future in as_completed(futures):
            total += future.result()
        
        return total
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document from its shard"""
        shard = self.get_shard_for_document(doc_id)
        return shard.delete_document(doc_id)
    
    def search(
        self,
        query: str,
        limit: int = 20,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search across all shards.
        
        Uses scatter-gather pattern to query all shards in parallel
        and merge results.
        
        Returns:
            Merged and ranked search results
        """
        # Query all shards in parallel
        futures = []
        for shard_id in self.router.route_query():
            future = self._executor.submit(
                self.shards[shard_id].search, query, limit, min_score
            )
            futures.append(future)
        
        # Gather results
        all_results = []
        for future in as_completed(futures):
            all_results.extend(future.result())
        
        # Merge and rank
        all_results.sort(key=lambda r: r.score, reverse=True)
        
        return all_results[:limit]
    
    def start_bulk_ingest(self):
        """
        Start bulk ingest mode.
        
        Disables compaction until finish_bulk_ingest is called.
        """
        self._bulk_mode = True
        for shard in self.shards.values():
            if shard.compaction:
                shard.compaction.start_bulk_ingest()
        
        logger.info("Started bulk ingest mode")
    
    def finish_bulk_ingest(self):
        """
        Finish bulk ingest mode.
        
        Runs final compaction on all shards.
        """
        self._bulk_mode = False
        
        # Run compaction on all shards in parallel
        futures = []
        for shard in self.shards.values():
            if shard.compaction:
                future = self._executor.submit(
                    shard.compaction.finish_bulk_ingest
                )
                futures.append(future)
        
        for future in as_completed(futures):
            future.result()
        
        logger.info("Finished bulk ingest mode")
    
    def run_compaction(self, force: bool = False):
        """Run compaction on all shards"""
        for shard in self.shards.values():
            shard.run_compaction(force)
    
    def save_all(self):
        """Save all shards to disk"""
        for shard in self.shards.values():
            shard.save()
        logger.info("All shards saved")
    
    def load_all(self):
        """Load all shards from disk"""
        for shard in self.shards.values():
            shard.load()
        logger.info("All shards loaded")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all shards"""
        shard_stats = [shard.get_stats() for shard in self.shards.values()]
        
        return {
            "num_shards": self.num_shards,
            "total_documents": sum(s.document_count for s in shard_stats),
            "total_ngrams": sum(s.ngram_count for s in shard_stats),
            "total_segments": sum(s.segment_count for s in shard_stats),
            "total_pending": sum(s.pending_messages for s in shard_stats),
            "shards": [
                {
                    "shard_id": s.shard_id,
                    "documents": s.document_count,
                    "ngrams": s.ngram_count,
                    "segments": s.segment_count,
                    "pending": s.pending_messages
                }
                for s in shard_stats
            ]
        }
    
    def process_event(self, event: DocumentEvent):
        """
        Process a document event.
        
        Called by consumers to index/delete documents.
        """
        if event.action == "delete":
            self.delete_document(event.document.id)
        else:
            self.index_document(event.document)
    
    def shutdown(self):
        """Shutdown the shard manager"""
        self._executor.shutdown(wait=True)
        self.save_all()
        logger.info("Shard manager shutdown complete")
