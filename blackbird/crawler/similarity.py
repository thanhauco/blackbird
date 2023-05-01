"""
MinHash Similarity for Blackbird Search Engine

Implements MinHash-based similarity estimation for repository deduplication
and building the similarity graph for optimal ingest ordering.
"""

import heapq
import random
from typing import List, Dict, Set, Optional, Tuple, Iterator
from dataclasses import dataclass, field
from collections import defaultdict
import structlog

try:
    import mmh3
    MMHASH_AVAILABLE = True
except ImportError:
    MMHASH_AVAILABLE = False
    import hashlib

from ..config import get_config

logger = structlog.get_logger()


def _hash_value(value: str, seed: int) -> int:
    """Hash a value with a seed"""
    if MMHASH_AVAILABLE:
        return mmh3.hash(value, seed) & 0xFFFFFFFF
    else:
        # Fallback to SHA-256 based hashing
        data = f"{seed}:{value}".encode()
        h = hashlib.sha256(data).digest()
        return int.from_bytes(h[:4], 'little')


@dataclass
class MinHashSignature:
    """
    MinHash signature for a repository.
    
    A compact representation of the repository's content
    that allows efficient similarity estimation.
    """
    repo_id: str
    signature: Tuple[int, ...]
    num_shingles: int = 0  # Number of unique items in the set
    
    def jaccard_similarity(self, other: "MinHashSignature") -> float:
        """
        Estimate Jaccard similarity with another signature.
        
        Jaccard = |A ∩ B| / |A ∪ B|
        Estimated as the fraction of matching hash values.
        """
        if len(self.signature) != len(other.signature):
            raise ValueError("Signatures must have same length")
        
        matches = sum(
            1 for a, b in zip(self.signature, other.signature)
            if a == b
        )
        return matches / len(self.signature)


@dataclass
class SimilarityEdge:
    """Edge in the similarity graph"""
    repo_a: str
    repo_b: str
    similarity: float
    
    @property
    def weight(self) -> float:
        """Weight for MST (lower = more similar)"""
        return 1.0 - self.similarity


@dataclass
class SimilarityGraph:
    """
    Graph of repository similarities.
    
    Nodes are repositories, edges are weighted by similarity.
    Used to compute MST for optimal ingest ordering.
    """
    nodes: Set[str] = field(default_factory=set)
    edges: List[SimilarityEdge] = field(default_factory=list)
    adjacency: Dict[str, List[Tuple[str, float]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    
    def add_node(self, repo_id: str):
        """Add a repository node"""
        self.nodes.add(repo_id)
    
    def add_edge(self, repo_a: str, repo_b: str, similarity: float):
        """Add a similarity edge between repositories"""
        if similarity <= 0:
            return  # Skip edges with no similarity
        
        edge = SimilarityEdge(repo_a, repo_b, similarity)
        self.edges.append(edge)
        
        self.adjacency[repo_a].append((repo_b, similarity))
        self.adjacency[repo_b].append((repo_a, similarity))
    
    def get_neighbors(self, repo_id: str) -> List[Tuple[str, float]]:
        """Get neighbors of a repository sorted by similarity (descending)"""
        neighbors = self.adjacency.get(repo_id, [])
        return sorted(neighbors, key=lambda x: -x[1])


@dataclass
class DeltaTree:
    """
    Delta tree for optimized repository crawling.
    
    Each repository is linked to its most similar parent,
    allowing delta-based crawling.
    """
    root: Optional[str] = None
    parent: Dict[str, Optional[str]] = field(default_factory=dict)
    children: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    
    def add_node(self, repo_id: str, parent_id: Optional[str] = None):
        """Add a repository to the tree"""
        self.parent[repo_id] = parent_id
        if parent_id:
            self.children[parent_id].append(repo_id)
        elif self.root is None:
            self.root = repo_id
    
    def get_parent(self, repo_id: str) -> Optional[str]:
        """Get parent of a repository"""
        return self.parent.get(repo_id)
    
    def get_children(self, repo_id: str) -> List[str]:
        """Get children of a repository"""
        return self.children.get(repo_id, [])
    
    def level_order_traversal(self) -> Iterator[str]:
        """
        Iterate through repositories in level order (BFS).
        
        This is the optimal order for ingest - parent repos
        are processed before children for efficient delta crawling.
        """
        if not self.root:
            return
        
        queue = [self.root]
        while queue:
            repo_id = queue.pop(0)
            yield repo_id
            queue.extend(self.children.get(repo_id, []))


class MinHashSimilarity:
    """
    MinHash-based similarity estimation for repositories.
    
    Uses MinHash (locality-sensitive hashing) to efficiently
    estimate Jaccard similarity between repositories based
    on their content.
    """
    
    def __init__(
        self,
        num_permutations: int = 128,
        similarity_threshold: float = 0.5,
        seed: int = 42
    ):
        """
        Initialize MinHash similarity estimator.
        
        Args:
            num_permutations: Number of hash functions (higher = more accurate)
            similarity_threshold: Minimum similarity to consider related
            seed: Random seed for reproducibility
        """
        config = get_config()
        
        self.num_permutations = num_permutations or config.MINHASH_NUM_PERM
        self.similarity_threshold = similarity_threshold or config.SIMILARITY_THRESHOLD
        
        # Generate random seeds for hash functions
        random.seed(seed)
        self.seeds = [random.randint(0, 2**32 - 1) for _ in range(self.num_permutations)]
        
        # Cache of computed signatures
        self._signatures: Dict[str, MinHashSignature] = {}
    
    def compute_signature(
        self,
        repo_id: str,
        shingles: Set[str]
    ) -> MinHashSignature:
        """
        Compute MinHash signature for a set of shingles.
        
        Shingles can be:
        - Blob hashes (for content-based similarity)
        - File paths (for structure-based similarity)
        - Ngrams from code (for code-based similarity)
        
        Args:
            repo_id: Repository identifier
            shingles: Set of string items representing the repository
            
        Returns:
            MinHashSignature for the repository
        """
        if not shingles:
            # Return empty signature
            signature = tuple([0xFFFFFFFF] * self.num_permutations)
            return MinHashSignature(repo_id, signature, 0)
        
        # Compute MinHash: for each permutation, find the minimum hash
        mins = [0xFFFFFFFF] * self.num_permutations
        
        for shingle in shingles:
            for i, seed in enumerate(self.seeds):
                h = _hash_value(shingle, seed)
                if h < mins[i]:
                    mins[i] = h
        
        signature = MinHashSignature(
            repo_id=repo_id,
            signature=tuple(mins),
            num_shingles=len(shingles)
        )
        
        self._signatures[repo_id] = signature
        return signature
    
    def compute_signature_from_blobs(
        self,
        repo_id: str,
        blob_hashes: Set[str]
    ) -> MinHashSignature:
        """
        Compute signature from Git blob hashes.
        
        This is the recommended approach for repository similarity
        as blob hashes represent unique content chunks.
        """
        return self.compute_signature(repo_id, blob_hashes)
    
    def estimate_similarity(
        self,
        sig1: MinHashSignature,
        sig2: MinHashSignature
    ) -> float:
        """
        Estimate Jaccard similarity between two repositories.
        """
        return sig1.jaccard_similarity(sig2)
    
    def build_similarity_graph(
        self,
        signatures: List[MinHashSignature]
    ) -> SimilarityGraph:
        """
        Build a similarity graph from repository signatures.
        
        Computes pairwise similarities and creates edges
        for pairs above the threshold.
        """
        graph = SimilarityGraph()
        
        # Add all nodes
        for sig in signatures:
            graph.add_node(sig.repo_id)
        
        # Compute pairwise similarities
        n = len(signatures)
        comparisons = 0
        edges_added = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                similarity = self.estimate_similarity(
                    signatures[i], signatures[j]
                )
                comparisons += 1
                
                if similarity >= self.similarity_threshold:
                    graph.add_edge(
                        signatures[i].repo_id,
                        signatures[j].repo_id,
                        similarity
                    )
                    edges_added += 1
        
        logger.info(
            "Built similarity graph",
            nodes=len(graph.nodes),
            edges=len(graph.edges),
            comparisons=comparisons
        )
        
        return graph
    
    def compute_mst(self, graph: SimilarityGraph) -> DeltaTree:
        """
        Compute Minimum Spanning Tree of the similarity graph.
        
        Uses Prim's algorithm to find the MST, which gives
        the optimal traversal order for delta-based crawling.
        
        Returns:
            DeltaTree with parent relationships
        """
        if not graph.nodes:
            return DeltaTree()
        
        tree = DeltaTree()
        visited = set()
        
        # Start with the node that has most connections (hub)
        start_node = max(
            graph.nodes,
            key=lambda n: len(graph.adjacency.get(n, []))
        )
        
        # Priority queue: (negative similarity, from_node, to_node)
        # Negative because heapq is a min-heap and we want max similarity
        heap = [(0, None, start_node)]
        
        while heap and len(visited) < len(graph.nodes):
            neg_sim, parent, node = heapq.heappop(heap)
            
            if node in visited:
                continue
            
            visited.add(node)
            tree.add_node(node, parent)
            
            # Add edges to unvisited neighbors
            for neighbor, similarity in graph.adjacency.get(node, []):
                if neighbor not in visited:
                    heapq.heappush(heap, (-similarity, node, neighbor))
        
        # Handle disconnected nodes (no similarity edges)
        for node in graph.nodes:
            if node not in visited:
                tree.add_node(node, start_node)
        
        logger.info(
            "Computed MST",
            root=tree.root,
            nodes=len(tree.parent)
        )
        
        return tree
    
    def get_ingest_order(
        self,
        signatures: List[MinHashSignature]
    ) -> List[Tuple[str, Optional[str]]]:
        """
        Get optimal repository ingest order.
        
        Returns list of (repo_id, parent_id) tuples in the order
        that repositories should be crawled for efficient delta ingest.
        """
        # Build similarity graph
        graph = self.build_similarity_graph(signatures)
        
        # Compute MST
        tree = self.compute_mst(graph)
        
        # Level-order traversal
        order = []
        for repo_id in tree.level_order_traversal():
            order.append((repo_id, tree.get_parent(repo_id)))
        
        return order
    
    def get_cached_signature(
        self,
        repo_id: str
    ) -> Optional[MinHashSignature]:
        """Get cached signature for a repository"""
        return self._signatures.get(repo_id)
    
    def clear_cache(self):
        """Clear the signature cache"""
        self._signatures.clear()


class LSHIndex:
    """
    Locality-Sensitive Hashing index for efficient similarity search.
    
    Allows finding similar repositories without computing all
    pairwise similarities (O(n) instead of O(n²)).
    """
    
    def __init__(
        self,
        num_bands: int = 16,
        rows_per_band: int = 8
    ):
        """
        Initialize LSH index.
        
        Args:
            num_bands: Number of bands for hashing
            rows_per_band: Number of rows per band
        """
        self.num_bands = num_bands
        self.rows_per_band = rows_per_band
        self.total_rows = num_bands * rows_per_band
        
        # Hash tables for each band
        self.buckets: List[Dict[int, Set[str]]] = [
            defaultdict(set) for _ in range(num_bands)
        ]
    
    def add(self, signature: MinHashSignature):
        """Add a signature to the index"""
        if len(signature.signature) != self.total_rows:
            raise ValueError(
                f"Signature must have {self.total_rows} elements, "
                f"got {len(signature.signature)}"
            )
        
        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            
            band = signature.signature[start:end]
            band_hash = hash(band)
            
            self.buckets[band_idx][band_hash].add(signature.repo_id)
    
    def find_candidates(
        self,
        signature: MinHashSignature
    ) -> Set[str]:
        """
        Find candidate similar repositories.
        
        Returns repositories that share at least one bucket
        with the query signature.
        """
        candidates = set()
        
        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            
            band = signature.signature[start:end]
            band_hash = hash(band)
            
            candidates.update(self.buckets[band_idx].get(band_hash, set()))
        
        # Remove self
        candidates.discard(signature.repo_id)
        
        return candidates
