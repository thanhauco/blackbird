"""
Partition Assignment for Blackbird Search Engine

Provides consistent hashing for shard assignment and load balancing.
"""

import hashlib
import bisect
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()


class ConsistentHash:
    """
    Consistent hashing ring for shard assignment.
    
    Provides stable mapping of documents to shards even when
    shards are added or removed.
    """
    
    def __init__(
        self,
        num_shards: int = 8,
        virtual_nodes: int = 150
    ):
        """
        Initialize the consistent hash ring.
        
        Args:
            num_shards: Number of shards
            virtual_nodes: Virtual nodes per shard (for better distribution)
        """
        self.num_shards = num_shards
        self.virtual_nodes = virtual_nodes
        
        # Ring: sorted list of (hash_value, shard_id)
        self.ring: List[int] = []
        self.hash_to_shard: Dict[int, int] = {}
        
        # Build the ring
        for shard_id in range(num_shards):
            self._add_shard(shard_id)
    
    def _hash(self, key: str) -> int:
        """Compute hash value for a key"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def _add_shard(self, shard_id: int):
        """Add a shard to the ring"""
        for i in range(self.virtual_nodes):
            key = f"shard-{shard_id}-node-{i}"
            hash_value = self._hash(key)
            
            bisect.insort(self.ring, hash_value)
            self.hash_to_shard[hash_value] = shard_id
    
    def get_shard(self, key: str) -> int:
        """
        Get the shard ID for a key.
        
        Uses consistent hashing to find the responsible shard.
        """
        if not self.ring:
            return 0
        
        hash_value = self._hash(key)
        
        # Find the first node >= hash_value
        idx = bisect.bisect_left(self.ring, hash_value)
        
        # Wrap around if needed
        if idx >= len(self.ring):
            idx = 0
        
        return self.hash_to_shard[self.ring[idx]]
    
    def get_shard_for_doc(self, doc_id: str) -> int:
        """Get shard for a document ID"""
        return self.get_shard(doc_id)
    
    def get_shard_for_repo(self, repo_id: str) -> int:
        """Get primary shard for a repository"""
        return self.get_shard(repo_id)


class PartitionAssigner:
    """
    Assigns documents to partitions/shards.
    
    Provides multiple strategies for partition assignment.
    """
    
    def __init__(
        self,
        num_shards: int = 8,
        strategy: str = "hash"
    ):
        """
        Initialize the partition assigner.
        
        Args:
            num_shards: Number of shards/partitions
            strategy: Assignment strategy ('hash', 'consistent', 'round_robin')
        """
        self.num_shards = num_shards
        self.strategy = strategy
        
        # For consistent hashing
        self._consistent_hash = ConsistentHash(num_shards)
        
        # For round-robin
        self._rr_counter = 0
        
        logger.info(
            "Partition assigner initialized",
            shards=num_shards,
            strategy=strategy
        )
    
    def get_partition(self, key: str) -> int:
        """
        Get partition for a key.
        
        Uses the configured strategy to determine partition.
        """
        if self.strategy == "hash":
            return self._hash_partition(key)
        elif self.strategy == "consistent":
            return self._consistent_hash.get_shard(key)
        elif self.strategy == "round_robin":
            return self._round_robin_partition()
        else:
            return self._hash_partition(key)
    
    def _hash_partition(self, key: str) -> int:
        """Simple hash-based partition assignment"""
        return hash(key) % self.num_shards
    
    def _round_robin_partition(self) -> int:
        """Round-robin partition assignment"""
        partition = self._rr_counter % self.num_shards
        self._rr_counter += 1
        return partition
    
    def get_all_partitions_for_query(self) -> List[int]:
        """
        Get all partitions that need to be queried.
        
        For search, we need to query all shards.
        """
        return list(range(self.num_shards))
    
    def rebalance(self, new_num_shards: int):
        """
        Rebalance for a new number of shards.
        
        Note: This changes partition assignments, requiring
        data migration.
        """
        old_num_shards = self.num_shards
        self.num_shards = new_num_shards
        self._consistent_hash = ConsistentHash(new_num_shards)
        
        logger.info(
            "Rebalanced partitions",
            old_shards=old_num_shards,
            new_shards=new_num_shards
        )


@dataclass
class ShardAssignment:
    """
    Represents the assignment of shards to nodes/workers.
    """
    shard_id: int
    node_id: str
    is_primary: bool = True
    replicas: List[str] = field(default_factory=list)


class ShardRouter:
    """
    Routes requests to the appropriate shards.
    
    Handles query distribution and result aggregation.
    """
    
    def __init__(self, num_shards: int = 8):
        self.num_shards = num_shards
        self.assigner = PartitionAssigner(num_shards, strategy="hash")
    
    def route_document(self, doc_id: str) -> int:
        """Route a document to its shard"""
        return self.assigner.get_partition(doc_id)
    
    def route_query(self) -> List[int]:
        """
        Get shards to query.
        
        For now, returns all shards (scatter-gather pattern).
        Could be optimized for specific query types.
        """
        return self.assigner.get_all_partitions_for_query()
    
    def route_by_repo(self, repo_id: str) -> List[int]:
        """
        Get shards containing a repository's documents.
        
        For now, returns all shards since documents are
        distributed by doc_id, not repo_id.
        """
        return self.assigner.get_all_partitions_for_query()
