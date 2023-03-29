"""
Compaction Engine for Blackbird Search Engine

Handles merging of small index segments into larger, more efficient ones.
Score-based sorting ensures relevant documents have lower IDs for fast iteration.
"""

import os
import time
import heapq
import pickle
import shutil
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Iterator, Tuple
from datetime import datetime
from collections import defaultdict
import structlog

from .index import InvertedIndex, PostingsList, Posting

logger = structlog.get_logger()


@dataclass
class IndexSegment:
    """
    Represents a single index segment on disk.
    
    Segments are the unit of compaction - smaller segments are
    merged into larger ones during compaction.
    """
    segment_id: str
    path: Path
    doc_count: int
    ngram_count: int
    size_bytes: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    generation: int = 0  # Compaction generation (incremented on merge)
    
    # In-memory index (loaded on demand)
    _index: Optional[InvertedIndex] = field(default=None, repr=False)
    
    @property
    def is_loaded(self) -> bool:
        return self._index is not None
    
    def load(self) -> InvertedIndex:
        """Load index from disk"""
        if self._index is None:
            self._index = InvertedIndex.load(self.path)
        return self._index
    
    def unload(self):
        """Unload index from memory"""
        self._index = None
    
    def delete(self):
        """Delete segment file from disk"""
        if self.path.exists():
            os.remove(self.path)
    
    def to_dict(self) -> Dict:
        return {
            "segment_id": self.segment_id,
            "path": str(self.path),
            "doc_count": self.doc_count,
            "ngram_count": self.ngram_count,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "generation": self.generation
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "IndexSegment":
        return cls(
            segment_id=data["segment_id"],
            path=Path(data["path"]),
            doc_count=data["doc_count"],
            ngram_count=data["ngram_count"],
            size_bytes=data["size_bytes"],
            created_at=datetime.fromisoformat(data["created_at"]),
            generation=data.get("generation", 0)
        )
    
    @classmethod
    def create_from_index(
        cls,
        index: InvertedIndex,
        segment_dir: Path,
        segment_id: str
    ) -> "IndexSegment":
        """Create a new segment from an in-memory index"""
        path = segment_dir / f"{segment_id}.idx"
        index.save(path)
        
        stats = index.get_stats()
        size_bytes = os.path.getsize(path)
        
        segment = cls(
            segment_id=segment_id,
            path=path,
            doc_count=stats["document_count"],
            ngram_count=stats["ngram_count"],
            size_bytes=size_bytes
        )
        segment._index = index
        return segment


@dataclass
class Tombstone:
    """
    Marks a deleted document.
    
    During compaction, tombstones are used to filter out
    deleted documents from merged segments.
    """
    doc_id: str
    deleted_at: datetime = field(default_factory=datetime.utcnow)
    segment_generation: int = 0  # Generation when deleted


class CompactionEngine:
    """
    Manages index segment compaction.
    
    Compaction merges smaller segments into larger ones:
    1. More efficient to query (fewer file opens)
    2. Easier to move around (fewer files)
    3. Postings are sorted by score for fast iteration
    """
    
    def __init__(
        self,
        segment_dir: Path,
        compaction_threshold: int = 10,
        max_segment_size_mb: int = 256,
        min_merge_segments: int = 3
    ):
        """
        Initialize the compaction engine.
        
        Args:
            segment_dir: Directory for storing segments
            compaction_threshold: Number of segments before compaction triggers
            max_segment_size_mb: Maximum segment size after compaction
            min_merge_segments: Minimum segments to merge at once
        """
        self.segment_dir = Path(segment_dir)
        self.segment_dir.mkdir(parents=True, exist_ok=True)
        
        self.compaction_threshold = compaction_threshold
        self.max_segment_size_bytes = max_segment_size_mb * 1024 * 1024
        self.min_merge_segments = min_merge_segments
        
        # Active segments
        self._segments: Dict[str, IndexSegment] = {}
        
        # Tombstones for deleted documents
        self._tombstones: Dict[str, Tombstone] = {}
        
        # Segment counter for IDs
        self._segment_counter = 0
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Load existing segments
        self._load_segments()
    
    def _load_segments(self):
        """Load segment metadata from disk"""
        meta_path = self.segment_dir / "segments.meta"
        if meta_path.exists():
            with open(meta_path, 'rb') as f:
                data = pickle.load(f)
                
            for seg_data in data.get("segments", []):
                segment = IndexSegment.from_dict(seg_data)
                if segment.path.exists():
                    self._segments[segment.segment_id] = segment
            
            for tomb_data in data.get("tombstones", []):
                doc_id = tomb_data["doc_id"]
                self._tombstones[doc_id] = Tombstone(
                    doc_id=doc_id,
                    deleted_at=datetime.fromisoformat(tomb_data["deleted_at"]),
                    segment_generation=tomb_data.get("segment_generation", 0)
                )
            
            self._segment_counter = data.get("counter", 0)
    
    def _save_metadata(self):
        """Save segment metadata to disk"""
        meta_path = self.segment_dir / "segments.meta"
        data = {
            "segments": [seg.to_dict() for seg in self._segments.values()],
            "tombstones": [
                {
                    "doc_id": t.doc_id,
                    "deleted_at": t.deleted_at.isoformat(),
                    "segment_generation": t.segment_generation
                }
                for t in self._tombstones.values()
            ],
            "counter": self._segment_counter
        }
        with open(meta_path, 'wb') as f:
            pickle.dump(data, f)
    
    def _generate_segment_id(self) -> str:
        """Generate a new segment ID"""
        self._segment_counter += 1
        timestamp = int(time.time() * 1000)
        return f"seg_{timestamp}_{self._segment_counter:06d}"
    
    def add_segment(self, index: InvertedIndex) -> IndexSegment:
        """
        Add a new index as a segment.
        
        Args:
            index: In-memory index to persist as segment
            
        Returns:
            Created IndexSegment
        """
        with self._lock:
            segment_id = self._generate_segment_id()
            segment = IndexSegment.create_from_index(
                index, self.segment_dir, segment_id
            )
            self._segments[segment_id] = segment
            self._save_metadata()
            
            logger.info(
                "Added new segment",
                segment_id=segment_id,
                doc_count=segment.doc_count,
                size_mb=segment.size_bytes / (1024 * 1024)
            )
            
            return segment
    
    def mark_deleted(self, doc_id: str):
        """Mark a document as deleted (add tombstone)"""
        with self._lock:
            max_gen = max(
                (seg.generation for seg in self._segments.values()),
                default=0
            )
            self._tombstones[doc_id] = Tombstone(
                doc_id=doc_id,
                segment_generation=max_gen
            )
            self._save_metadata()
    
    def should_compact(self) -> bool:
        """Check if compaction should run"""
        with self._lock:
            return len(self._segments) >= self.compaction_threshold
    
    def compact(self, force: bool = False) -> Optional[IndexSegment]:
        """
        Run compaction to merge segments.
        
        Args:
            force: Run even if below threshold
            
        Returns:
            New merged segment, or None if no compaction needed
        """
        with self._lock:
            if not force and not self.should_compact():
                return None
            
            if len(self._segments) < self.min_merge_segments:
                return None
            
            logger.info(
                "Starting compaction",
                segment_count=len(self._segments),
                tombstone_count=len(self._tombstones)
            )
            
            # Select segments to merge
            # Strategy: merge smallest segments first (tiered compaction)
            segments_to_merge = self._select_segments_for_merge()
            
            if len(segments_to_merge) < self.min_merge_segments:
                return None
            
            # Merge segments
            merged_index = self._merge_segments(segments_to_merge)
            
            if merged_index.get_stats()["document_count"] == 0:
                # All documents were deleted
                for seg in segments_to_merge:
                    seg.delete()
                    del self._segments[seg.segment_id]
                self._save_metadata()
                return None
            
            # Create new segment from merged index
            new_segment = self.add_segment(merged_index)
            new_segment.generation = max(
                seg.generation for seg in segments_to_merge
            ) + 1
            
            # Remove old segments
            for seg in segments_to_merge:
                seg.delete()
                del self._segments[seg.segment_id]
            
            # Clean up old tombstones
            self._cleanup_tombstones(new_segment.generation)
            
            self._save_metadata()
            
            logger.info(
                "Compaction complete",
                merged_segments=len(segments_to_merge),
                new_segment_id=new_segment.segment_id,
                doc_count=new_segment.doc_count,
                size_mb=new_segment.size_bytes / (1024 * 1024)
            )
            
            return new_segment
    
    def _select_segments_for_merge(self) -> List[IndexSegment]:
        """
        Select segments to merge using tiered compaction strategy.
        
        Prefers merging smaller segments together.
        """
        # Sort by size (smallest first)
        sorted_segments = sorted(
            self._segments.values(),
            key=lambda s: s.size_bytes
        )
        
        selected = []
        total_size = 0
        
        for segment in sorted_segments:
            if total_size + segment.size_bytes > self.max_segment_size_bytes:
                break
            selected.append(segment)
            total_size += segment.size_bytes
            
            # Limit number of segments to merge at once
            if len(selected) >= 10:
                break
        
        return selected
    
    def _merge_segments(
        self,
        segments: List[IndexSegment]
    ) -> InvertedIndex:
        """
        Merge multiple segments into one.
        
        - Combines all posting lists
        - Filters out tombstoned documents
        - Sorts postings by score
        """
        # Load all segments
        for seg in segments:
            seg.load()
        
        # Create new index
        # Use ngram size from first segment
        first_index = segments[0]._index
        merged = InvertedIndex(
            ngram_size=first_index.tokenizer.n,
            symbol_boost=first_index.symbol_boost
        )
        
        # Merge all indices
        for seg in segments:
            merged.merge(seg._index)
        
        # Remove tombstoned documents
        for doc_id in list(self._tombstones.keys()):
            merged.remove_document(doc_id)
        
        # Ensure postings are sorted by score
        for postings in merged._index.values():
            postings.sort()
        
        # Unload to free memory
        for seg in segments:
            seg.unload()
        
        return merged
    
    def _cleanup_tombstones(self, min_generation: int):
        """Remove tombstones older than all segments"""
        to_remove = [
            doc_id for doc_id, tomb in self._tombstones.items()
            if tomb.segment_generation < min_generation
        ]
        for doc_id in to_remove:
            del self._tombstones[doc_id]
    
    def get_all_segments(self) -> List[IndexSegment]:
        """Get all active segments"""
        with self._lock:
            return list(self._segments.values())
    
    def get_stats(self) -> Dict:
        """Get compaction statistics"""
        with self._lock:
            total_size = sum(seg.size_bytes for seg in self._segments.values())
            total_docs = sum(seg.doc_count for seg in self._segments.values())
            
            return {
                "segment_count": len(self._segments),
                "total_size_bytes": total_size,
                "total_size_mb": total_size / (1024 * 1024),
                "total_documents": total_docs,
                "tombstone_count": len(self._tombstones),
                "segments": [seg.to_dict() for seg in self._segments.values()]
            }
    
    def search_all_segments(
        self,
        query: str,
        limit: int = 20
    ) -> List:
        """
        Search across all segments and merge results.
        
        Uses a min-heap to efficiently merge sorted results.
        """
        with self._lock:
            # Load all segments
            for seg in self._segments.values():
                seg.load()
            
            # Search each segment
            all_results = []
            for seg in self._segments.values():
                results = seg._index.search(query, limit=limit)
                all_results.extend(results)
            
            # Filter tombstoned documents
            all_results = [
                r for r in all_results
                if r.doc_id not in self._tombstones
            ]
            
            # Sort by score and limit
            all_results.sort(key=lambda r: r.score, reverse=True)
            return all_results[:limit]


class DelayedCompactionEngine(CompactionEngine):
    """
    Compaction engine with delayed compaction for initial ingest.
    
    During bulk loading, accumulates segments without compacting,
    then runs a single massive compaction at the end.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._delay_compaction = False
        self._pending_segments: List[IndexSegment] = []
    
    def start_bulk_ingest(self):
        """Start bulk ingest mode - delay compaction"""
        with self._lock:
            self._delay_compaction = True
            logger.info("Starting bulk ingest mode - compaction delayed")
    
    def finish_bulk_ingest(self) -> Optional[IndexSegment]:
        """
        Finish bulk ingest mode and run final compaction.
        
        Returns:
            Final merged segment
        """
        with self._lock:
            self._delay_compaction = False
            logger.info(
                "Finishing bulk ingest mode",
                segment_count=len(self._segments)
            )
            
            # Run final compaction
            return self.compact(force=True)
    
    def should_compact(self) -> bool:
        """Check if compaction should run (respects delay mode)"""
        if self._delay_compaction:
            return False
        return super().should_compact()
