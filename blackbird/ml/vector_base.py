"""
Vector Store Base Classes and Utilities

Provides abstract interfaces and helpers for vector storage.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from dataclasses import dataclass
import numpy as np


@dataclass
class VectorDocument:
    """Document with vector representation"""
    doc_id: str
    vector: np.ndarray
    metadata: Dict[str, Any]


class BaseVectorStore(ABC):
    """Abstract base class for vector stores"""
    
    @abstractmethod
    def add(self, doc_id: str, vector: np.ndarray, metadata: Optional[Dict] = None):
        """Add a vector to the store"""
        pass
    
    @abstractmethod
    def search(self, query_vector: np.ndarray, k: int = 10) -> List[tuple]:
        """Search for similar vectors"""
        pass
    
    @abstractmethod
    def delete(self, doc_id: str) -> bool:
        """Delete a vector from the store"""
        pass
    
    @abstractmethod
    def __len__(self) -> int:
        """Return number of vectors in store"""
        pass


def normalize_vector(v: np.ndarray) -> np.ndarray:
    """Normalize vector to unit length"""
    norm = np.linalg.norm(v)
    if norm > 0:
        return v / norm
    return v


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors"""
    a_norm = normalize_vector(a)
    b_norm = normalize_vector(b)
    return float(np.dot(a_norm, b_norm))


def batch_cosine_similarity(query: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and batch of vectors"""
    query_norm = normalize_vector(query)
    # Normalize each vector in the batch
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Avoid division by zero
    vectors_norm = vectors / norms
    return np.dot(vectors_norm, query_norm)
