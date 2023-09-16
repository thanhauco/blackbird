"""
Semantic Code Search using Embeddings

Provides neural search capabilities using sentence-transformers
for code understanding and similarity matching.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pickle
import threading
import structlog

logger = structlog.get_logger()

# Try to import ML libraries
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available, semantic search disabled")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("faiss not available, using numpy fallback")


@dataclass
class CodeEmbedding:
    """
    Embedding representation of a code document.
    """
    doc_id: str
    embedding: np.ndarray
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticSearchResult:
    """
    Result from semantic search.
    """
    doc_id: str
    score: float
    distance: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class CodeEmbedder:
    """
    Generates embeddings for code using pre-trained models.
    
    Uses CodeBERT or similar models optimized for code understanding.
    """
    
    # Models optimized for code
    CODE_MODELS = [
        "microsoft/codebert-base",
        "microsoft/graphcodebert-base",
        "sentence-transformers/all-MiniLM-L6-v2",  # Fallback
    ]
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "cpu",
        max_length: int = 512
    ):
        """
        Initialize the code embedder.
        
        Args:
            model_name: Name of the model to use
            device: Device to run on ('cpu' or 'cuda')
            max_length: Maximum token length
        """
        self.model_name = model_name or "sentence-transformers/all-MiniLM-L6-v2"
        self.device = device
        self.max_length = max_length
        self.model = None
        self._lock = threading.Lock()
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self._load_model()
    
    def _load_model(self):
        """Load the embedding model"""
        try:
            self.model = SentenceTransformer(self.model_name, device=self.device)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(
                "Loaded embedding model",
                model=self.model_name,
                dim=self.embedding_dim
            )
        except Exception as e:
            logger.error("Failed to load model", error=str(e))
            self.model = None
    
    def embed(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for a single text.
        """
        if not self.model:
            return None
        
        with self._lock:
            embedding = self.model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False
            )
        return embedding
    
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts.
        """
        if not self.model:
            return []
        
        with self._lock:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=True
            )
        return list(embeddings)
    
    def embed_code(self, code: str, language: str = "") -> Optional[np.ndarray]:
        """
        Generate embedding for code with language context.
        """
        # Add language prefix for better understanding
        if language:
            text = f"[{language}] {code}"
        else:
            text = code
        
        # Truncate if too long
        if len(text) > self.max_length * 4:  # Rough char estimate
            text = text[:self.max_length * 4]
        
        return self.embed(text)
    
    def embed_query(self, query: str) -> Optional[np.ndarray]:
        """
        Generate embedding for a search query.
        """
        # Queries might benefit from different processing
        return self.embed(f"search: {query}")


class VectorStore:
    """
    Vector store for efficient similarity search.
    
    Uses FAISS for fast approximate nearest neighbor search,
    with numpy fallback for smaller datasets.
    """
    
    def __init__(
        self,
        dimension: int = 384,
        index_type: str = "flat",
        store_path: Optional[Path] = None
    ):
        """
        Initialize the vector store.
        
        Args:
            dimension: Embedding dimension
            index_type: FAISS index type ('flat', 'ivf', 'hnsw')
            store_path: Path to persist the index
        """
        self.dimension = dimension
        self.index_type = index_type
        self.store_path = Path(store_path) if store_path else None
        
        # Document ID mapping
        self.id_to_idx: Dict[str, int] = {}
        self.idx_to_id: Dict[int, str] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
        
        # Initialize index
        self.index = None
        self._init_index()
        
        self._lock = threading.Lock()
    
    def _init_index(self):
        """Initialize the FAISS index"""
        if FAISS_AVAILABLE:
            if self.index_type == "flat":
                self.index = faiss.IndexFlatIP(self.dimension)  # Inner product
            elif self.index_type == "ivf":
                quantizer = faiss.IndexFlatIP(self.dimension)
                self.index = faiss.IndexIVFFlat(quantizer, self.dimension, 100)
            elif self.index_type == "hnsw":
                self.index = faiss.IndexHNSWFlat(self.dimension, 32)
            else:
                self.index = faiss.IndexFlatIP(self.dimension)
            
            logger.info("Initialized FAISS index", type=self.index_type)
        else:
            # Numpy fallback
            self.vectors = []
            logger.info("Using numpy fallback for vector store")
    
    def add(
        self,
        doc_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Add a document embedding to the store"""
        with self._lock:
            # Normalize for cosine similarity
            embedding = embedding / np.linalg.norm(embedding)
            
            idx = len(self.id_to_idx)
            self.id_to_idx[doc_id] = idx
            self.idx_to_id[idx] = doc_id
            
            if metadata:
                self.metadata[doc_id] = metadata
            
            if FAISS_AVAILABLE:
                self.index.add(embedding.reshape(1, -1).astype('float32'))
            else:
                self.vectors.append(embedding)
    
    def add_batch(
        self,
        embeddings: List[CodeEmbedding]
    ):
        """Add multiple embeddings"""
        for emb in embeddings:
            self.add(emb.doc_id, emb.embedding, emb.metadata)
    
    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10,
        min_score: float = 0.0
    ) -> List[SemanticSearchResult]:
        """
        Search for similar documents.
        
        Args:
            query_embedding: Query vector
            k: Number of results
            min_score: Minimum similarity score
            
        Returns:
            List of search results
        """
        with self._lock:
            # Normalize query
            query_embedding = query_embedding / np.linalg.norm(query_embedding)
            
            if FAISS_AVAILABLE and self.index.ntotal > 0:
                distances, indices = self.index.search(
                    query_embedding.reshape(1, -1).astype('float32'),
                    min(k, self.index.ntotal)
                )
                distances = distances[0]
                indices = indices[0]
            elif self.vectors:
                # Numpy fallback
                vectors = np.array(self.vectors)
                similarities = np.dot(vectors, query_embedding)
                indices = np.argsort(similarities)[::-1][:k]
                distances = similarities[indices]
            else:
                return []
            
            results = []
            for dist, idx in zip(distances, indices):
                if idx < 0:  # FAISS returns -1 for not found
                    continue
                
                doc_id = self.idx_to_id.get(int(idx))
                if not doc_id:
                    continue
                
                score = float(dist)  # For IP, distance = similarity
                if score < min_score:
                    continue
                
                results.append(SemanticSearchResult(
                    doc_id=doc_id,
                    score=score,
                    distance=1.0 - score,
                    metadata=self.metadata.get(doc_id, {})
                ))
            
            return results
    
    def remove(self, doc_id: str) -> bool:
        """Remove a document from the store"""
        # Note: FAISS doesn't support efficient removal
        # This marks for future rebuild
        if doc_id in self.id_to_idx:
            del self.id_to_idx[doc_id]
            if doc_id in self.metadata:
                del self.metadata[doc_id]
            return True
        return False
    
    def save(self, path: Optional[Path] = None):
        """Save the index to disk"""
        path = path or self.store_path
        if not path:
            return
        
        path.mkdir(parents=True, exist_ok=True)
        
        # Save FAISS index
        if FAISS_AVAILABLE:
            faiss.write_index(self.index, str(path / "vectors.index"))
        else:
            np.save(path / "vectors.npy", np.array(self.vectors))
        
        # Save mappings
        with open(path / "mappings.pkl", "wb") as f:
            pickle.dump({
                "id_to_idx": self.id_to_idx,
                "idx_to_id": self.idx_to_id,
                "metadata": self.metadata
            }, f)
        
        logger.info("Saved vector store", path=str(path))
    
    def load(self, path: Optional[Path] = None):
        """Load the index from disk"""
        path = path or self.store_path
        if not path or not path.exists():
            return
        
        # Load FAISS index
        index_path = path / "vectors.index"
        if FAISS_AVAILABLE and index_path.exists():
            self.index = faiss.read_index(str(index_path))
        elif (path / "vectors.npy").exists():
            self.vectors = list(np.load(path / "vectors.npy"))
        
        # Load mappings
        mappings_path = path / "mappings.pkl"
        if mappings_path.exists():
            with open(mappings_path, "rb") as f:
                data = pickle.load(f)
                self.id_to_idx = data["id_to_idx"]
                self.idx_to_id = data["idx_to_id"]
                self.metadata = data.get("metadata", {})
        
        logger.info("Loaded vector store", path=str(path))
    
    def __len__(self) -> int:
        return len(self.id_to_idx)


class SemanticSearchEngine:
    """
    High-level semantic search engine.
    
    Combines code embedding and vector search for
    neural code search capabilities.
    """
    
    def __init__(
        self,
        embedder: Optional[CodeEmbedder] = None,
        store: Optional[VectorStore] = None,
        store_path: Optional[Path] = None
    ):
        """
        Initialize the semantic search engine.
        """
        self.embedder = embedder or CodeEmbedder()
        
        dim = getattr(self.embedder, 'embedding_dim', 384)
        self.store = store or VectorStore(dimension=dim, store_path=store_path)
        
        logger.info("Semantic search engine initialized")
    
    def index_document(
        self,
        doc_id: str,
        content: str,
        language: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Index a document for semantic search.
        """
        embedding = self.embedder.embed_code(content, language)
        if embedding is None:
            return False
        
        meta = metadata or {}
        meta["language"] = language
        
        self.store.add(doc_id, embedding, meta)
        return True
    
    def index_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 32
    ) -> int:
        """
        Index multiple documents.
        
        Args:
            documents: List of dicts with 'id', 'content', 'language'
            batch_size: Batch size for embedding
            
        Returns:
            Number of documents indexed
        """
        texts = []
        doc_data = []
        
        for doc in documents:
            lang = doc.get("language", "")
            content = doc.get("content", "")
            
            if lang:
                text = f"[{lang}] {content}"
            else:
                text = content
            
            texts.append(text[:2048])  # Truncate
            doc_data.append(doc)
        
        embeddings = self.embedder.embed_batch(texts, batch_size)
        
        count = 0
        for emb, doc in zip(embeddings, doc_data):
            self.store.add(
                doc["id"],
                emb,
                {"language": doc.get("language", "")}
            )
            count += 1
        
        logger.info("Indexed documents for semantic search", count=count)
        return count
    
    def search(
        self,
        query: str,
        k: int = 10,
        min_score: float = 0.5
    ) -> List[SemanticSearchResult]:
        """
        Perform semantic search.
        """
        query_embedding = self.embedder.embed_query(query)
        if query_embedding is None:
            return []
        
        return self.store.search(query_embedding, k, min_score)
    
    def save(self):
        """Save the index"""
        self.store.save()
    
    def load(self):
        """Load the index"""
        self.store.load()
