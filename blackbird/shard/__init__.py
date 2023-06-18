"""
Blackbird Shard Module

Manages distributed index shards for scalable search.
"""

from .manager import ShardManager, Shard
from .partition import PartitionAssigner, ConsistentHash

__all__ = [
    "ShardManager",
    "Shard",
    "PartitionAssigner",
    "ConsistentHash"
]
