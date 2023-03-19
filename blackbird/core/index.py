"""
Inverted Index for Blackbird Search Engine

Implements ngram-based inverted index with posting lists for
efficient substring search across code documents.
"""

import os
import json
import heapq
import pickle
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Iterator, Tuple, Any
from collections import defaultdict
import bisect

from .ngram import NgramTokenizer
from .document import CodeDocument, Symbol, SymbolType


@dataclass
class Posting:
    """
    A posting list entry representing a document containing an ngram.
    """
    doc_id: str
    score: float = 1.0
    positions: List[int] = field(default_factory=list)  # Positions of ngram in doc
    is_symbol: bool = False  # True if ngram is from a symbol name
    
    def __lt__(self, other):
        # Sort by score descending, then doc_id for consistency
        if self.score != other.score:
            return self.score > other.score
        return self.doc_id < other.doc_id


class PostingsList:
    """
    Sorted list of postings for an ngram.
    
    Postings are sorted by score (descending) so that lazy iteration
    returns the most relevant documents first.
    """
    
    def __init__(self):
        self._postings: List[Posting] = []
        self._doc_index: Dict[str, int] = {}  # doc_id -> position in list
        self._sorted = True
    
    def add(self, posting: Posting):
        """Add a posting to the list"""
        if posting.doc_id in self._doc_index:
            # Update existing posting
            idx = self._doc_index[posting.doc_id]
            existing = self._postings[idx]
            existing.score = max(existing.score, posting.score)
            existing.positions.extend(posting.positions)
            existing.is_symbol = existing.is_symbol or posting.is_symbol
            self._sorted = False
        else:
            self._postings.append(posting)
            self._doc_index[posting.doc_id] = len(self._postings) - 1
            self._sorted = False
    
    def remove(self, doc_id: str) -> bool:
        """Remove a posting by doc_id. Returns True if found."""
        if doc_id not in self._doc_index:
            return False
        
        idx = self._doc_index[doc_id]
        # Swap with last and pop for O(1) removal
        if idx < len(self._postings) - 1:
            self._postings[idx] = self._postings[-1]
            self._doc_index[self._postings[idx].doc_id] = idx
        
        self._postings.pop()
        del self._doc_index[doc_id]
        self._sorted = False
        return True
    
    def get(self, doc_id: str) -> Optional[Posting]:
        """Get posting by doc_id"""
        if doc_id not in self._doc_index:
            return None
        return self._postings[self._doc_index[doc_id]]
    
    def sort(self):
        """Sort postings by score descending"""
        if not self._sorted:
            self._postings.sort()
            self._doc_index = {p.doc_id: i for i, p in enumerate(self._postings)}
            self._sorted = True
    
    def __len__(self) -> int:
        return len(self._postings)
    
    def __iter__(self) -> Iterator[Posting]:
        self.sort()
        return iter(self._postings)
    
    def get_doc_ids(self) -> Set[str]:
        """Get all document IDs in this posting list"""
        return set(self._doc_index.keys())
    
    def merge(self, other: "PostingsList"):
        """Merge another posting list into this one"""
        for posting in other._postings:
            self.add(posting)
    
    def to_dict(self) -> Dict:
        return {
            "postings": [
                {
                    "doc_id": p.doc_id,
                    "score": p.score,
                    "positions": p.positions,
                    "is_symbol": p.is_symbol
                }
                for p in self._postings
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PostingsList":
        pl = cls()
        for p in data.get("postings", []):
            pl.add(Posting(
                doc_id=p["doc_id"],
                score=p["score"],
                positions=p.get("positions", []),
                is_symbol=p.get("is_symbol", False)
            ))
        return pl


@dataclass
class SearchResult:
    """
    A search result with document ID and relevance score.
    """
    doc_id: str
    score: float
    matched_ngrams: int = 0
    total_ngrams: int = 0
    has_symbol_match: bool = False
    snippet: str = ""
    highlights: List[Tuple[int, int]] = field(default_factory=list)
    
    # Document metadata (populated during result enrichment)
    repo_id: str = ""
    path: str = ""
    language: str = ""
    
    def __lt__(self, other):
        return self.score > other.score  # Higher score first


class InvertedIndex:
    """
    Ngram-based inverted index for code search.
    
    This is the core data structure that maps ngrams to documents.
    Supports efficient intersection for substring matching.
    """
    
    def __init__(
        self,
        ngram_size: int = 3,
        symbol_boost: float = 2.0,
        index_path: Optional[Path] = None
    ):
        """
        Initialize the inverted index.
        
        Args:
            ngram_size: Size of ngrams (default 3 for trigrams)
            symbol_boost: Score multiplier for symbol matches
            index_path: Path for persistence (optional)
        """
        self.tokenizer = NgramTokenizer(n=ngram_size)
        self.symbol_boost = symbol_boost
        self.index_path = index_path
        
        # Main index: ngram -> PostingsList
        self._index: Dict[str, PostingsList] = defaultdict(PostingsList)
        
        # Document store: doc_id -> metadata
        self._documents: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self._doc_count = 0
        self._ngram_count = 0
        
        # Thread safety
        self._lock = threading.RLock()
    
    def add_document(
        self,
        document: CodeDocument,
        boost: float = 1.0
    ) -> bool:
        """
        Index a document.
        
        Args:
            document: The code document to index
            boost: Additional score boost for this document
            
        Returns:
            True if document was added (not duplicate)
        """
        with self._lock:
            # Check for duplicate
            if document.id in self._documents:
                return False
            
            # Store document metadata
            self._documents[document.id] = {
                "repo_id": document.repo_id,
                "path": document.path,
                "language": document.language,
                "blob_hash": document.blob_hash,
                "size_bytes": document.size_bytes,
                "line_count": document.line_count,
                "symbol_names": document.get_symbol_names()
            }
            
            base_score = document.score * boost
            
            # Index content ngrams
            content_ngrams = self.tokenizer.tokenize_code(document.content)
            for i, ngram in enumerate(content_ngrams):
                posting = Posting(
                    doc_id=document.id,
                    score=base_score,
                    positions=[i],
                    is_symbol=False
                )
                self._index[ngram].add(posting)
            
            # Index symbol names with boost
            for symbol in document.symbols:
                symbol_ngrams = self.tokenizer.tokenize(symbol.name)
                for ngram in symbol_ngrams:
                    posting = Posting(
                        doc_id=document.id,
                        score=base_score * self.symbol_boost,
                        positions=[],
                        is_symbol=True
                    )
                    self._index[ngram].add(posting)
            
            self._doc_count += 1
            self._ngram_count = len(self._index)
            
            return True
    
    def remove_document(self, doc_id: str) -> bool:
        """
        Remove a document from the index.
        
        Returns:
            True if document was found and removed
        """
        with self._lock:
            if doc_id not in self._documents:
                return False
            
            # Remove from all posting lists
            empty_ngrams = []
            for ngram, postings in self._index.items():
                postings.remove(doc_id)
                if len(postings) == 0:
                    empty_ngrams.append(ngram)
            
            # Clean up empty posting lists
            for ngram in empty_ngrams:
                del self._index[ngram]
            
            del self._documents[doc_id]
            self._doc_count -= 1
            self._ngram_count = len(self._index)
            
            return True
    
    def search(
        self,
        query: str,
        limit: int = 20,
        min_score: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for documents matching the query.
        
        Uses ngram intersection to find documents containing all
        ngrams from the query, then scores and ranks results.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            min_score: Minimum score threshold
            
        Returns:
            List of SearchResult objects, sorted by score
        """
        if not query:
            return []
        
        # Generate query ngrams
        query_ngrams = self.tokenizer.tokenize_query(query)
        
        if not query_ngrams:
            return []
        
        with self._lock:
            # Get posting lists for all query ngrams
            posting_lists = []
            for ngram in query_ngrams:
                if ngram in self._index:
                    posting_lists.append(self._index[ngram])
                else:
                    # Ngram not in index - no matches possible
                    return []
            
            # Sort by list size for efficient intersection
            posting_lists.sort(key=len)
            
            # Intersect posting lists
            if not posting_lists:
                return []
            
            # Start with smallest list
            candidate_docs = posting_lists[0].get_doc_ids()
            
            # Intersect with remaining lists
            for pl in posting_lists[1:]:
                candidate_docs &= pl.get_doc_ids()
                if not candidate_docs:
                    return []
            
            # Score candidates
            results = []
            for doc_id in candidate_docs:
                score = 0.0
                has_symbol_match = False
                matched_ngrams = 0
                
                for ngram in query_ngrams:
                    posting = self._index[ngram].get(doc_id)
                    if posting:
                        score += posting.score
                        matched_ngrams += 1
                        if posting.is_symbol:
                            has_symbol_match = True
                
                # Normalize score by query length
                normalized_score = score / len(query_ngrams)
                
                if normalized_score >= min_score:
                    doc_meta = self._documents.get(doc_id, {})
                    results.append(SearchResult(
                        doc_id=doc_id,
                        score=normalized_score,
                        matched_ngrams=matched_ngrams,
                        total_ngrams=len(query_ngrams),
                        has_symbol_match=has_symbol_match,
                        repo_id=doc_meta.get("repo_id", ""),
                        path=doc_meta.get("path", ""),
                        language=doc_meta.get("language", "")
                    ))
            
            # Sort by score and limit
            results.sort()
            return results[:limit]
    
    def search_with_ranking(
        self,
        query: str,
        limit: int = 20,
        exact_match_bonus: float = 5.0
    ) -> List[SearchResult]:
        """
        Search with advanced ranking including exact match bonus.
        """
        results = self.search(query, limit * 2)  # Get more for re-ranking
        
        # Re-rank with exact match bonus
        # This would require fetching actual document content
        # For now, just return basic results
        return results[:limit]
    
    def get_document_metadata(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get stored metadata for a document"""
        return self._documents.get(doc_id)
    
    def contains_document(self, doc_id: str) -> bool:
        """Check if document is in index"""
        return doc_id in self._documents
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        with self._lock:
            total_postings = sum(len(pl) for pl in self._index.values())
            return {
                "document_count": self._doc_count,
                "ngram_count": self._ngram_count,
                "total_postings": total_postings,
                "avg_postings_per_ngram": total_postings / max(1, self._ngram_count)
            }
    
    def merge(self, other: "InvertedIndex"):
        """
        Merge another index into this one.
        
        Used during compaction to combine smaller indices.
        """
        with self._lock:
            # Merge documents
            self._documents.update(other._documents)
            
            # Merge posting lists
            for ngram, postings in other._index.items():
                self._index[ngram].merge(postings)
            
            self._doc_count = len(self._documents)
            self._ngram_count = len(self._index)
    
    def save(self, path: Optional[Path] = None):
        """Save index to disk"""
        save_path = path or self.index_path
        if not save_path:
            raise ValueError("No index path specified")
        
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._lock:
            data = {
                "ngram_size": self.tokenizer.n,
                "symbol_boost": self.symbol_boost,
                "documents": self._documents,
                "index": {
                    ngram: pl.to_dict()
                    for ngram, pl in self._index.items()
                }
            }
            
            with open(save_path, 'wb') as f:
                pickle.dump(data, f)
    
    @classmethod
    def load(cls, path: Path) -> "InvertedIndex":
        """Load index from disk"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        
        index = cls(
            ngram_size=data["ngram_size"],
            symbol_boost=data["symbol_boost"],
            index_path=path
        )
        
        index._documents = data["documents"]
        index._index = defaultdict(PostingsList)
        
        for ngram, pl_data in data["index"].items():
            index._index[ngram] = PostingsList.from_dict(pl_data)
        
        index._doc_count = len(index._documents)
        index._ngram_count = len(index._index)
        
        return index
    
    def clear(self):
        """Clear all data from the index"""
        with self._lock:
            self._index.clear()
            self._documents.clear()
            self._doc_count = 0
            self._ngram_count = 0


class LazySearchIterator:
    """
    Lazy iterator for search results.
    
    Returns results one at a time, fetching more only as needed.
    Useful for implementing pagination efficiently.
    """
    
    def __init__(
        self,
        index: InvertedIndex,
        query: str,
        batch_size: int = 50
    ):
        self.index = index
        self.query = query
        self.batch_size = batch_size
        self._offset = 0
        self._buffer: List[SearchResult] = []
        self._exhausted = False
    
    def __iter__(self):
        return self
    
    def __next__(self) -> SearchResult:
        if not self._buffer and not self._exhausted:
            self._fetch_batch()
        
        if not self._buffer:
            raise StopIteration
        
        return self._buffer.pop(0)
    
    def _fetch_batch(self):
        """Fetch next batch of results"""
        results = self.index.search(
            self.query,
            limit=self._offset + self.batch_size
        )
        
        # Get results after offset
        self._buffer = results[self._offset:]
        self._offset += len(self._buffer)
        
        if len(self._buffer) < self.batch_size:
            self._exhausted = True
