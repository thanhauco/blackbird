"""
In-Memory Message Queue for Blackbird Search Engine

Simulates Kafka-like message queuing for event-driven indexing.
Provides partitioned topics with ordered message delivery.
"""

import time
import threading
from typing import List, Dict, Optional, Any, Iterator, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime
from queue import Queue, Empty
import structlog

logger = structlog.get_logger()


@dataclass
class Message:
    """
    A message in the queue.
    
    Similar to Kafka's ProducerRecord/ConsumerRecord.
    """
    key: str  # Used for partitioning
    value: Any  # Message payload
    topic: str
    partition: int = 0
    offset: int = 0
    timestamp: float = field(default_factory=time.time)
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class Partition:
    """
    A partition within a topic.
    
    Messages in a partition are ordered and assigned sequential offsets.
    """
    partition_id: int
    messages: List[Message] = field(default_factory=list)
    next_offset: int = 0
    
    # Lock for thread-safe access
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def append(self, message: Message) -> int:
        """Append a message and return its offset"""
        with self._lock:
            message.offset = self.next_offset
            message.partition = self.partition_id
            self.messages.append(message)
            self.next_offset += 1
            return message.offset
    
    def get(self, offset: int) -> Optional[Message]:
        """Get message at offset"""
        with self._lock:
            if offset < 0 or offset >= len(self.messages):
                return None
            return self.messages[offset]
    
    def get_range(
        self,
        start_offset: int,
        max_messages: int = 100
    ) -> List[Message]:
        """Get messages from start_offset"""
        with self._lock:
            if start_offset < 0:
                start_offset = 0
            end_offset = min(start_offset + max_messages, len(self.messages))
            return self.messages[start_offset:end_offset]
    
    def __len__(self) -> int:
        return len(self.messages)


class Topic:
    """
    A topic with multiple partitions.
    
    Messages are distributed across partitions based on key hash.
    """
    
    def __init__(self, name: str, num_partitions: int = 8):
        self.name = name
        self.num_partitions = num_partitions
        self.partitions = [
            Partition(partition_id=i)
            for i in range(num_partitions)
        ]
        self._lock = threading.Lock()
    
    def get_partition(self, key: str) -> int:
        """Get partition ID for a key (consistent hashing)"""
        return hash(key) % self.num_partitions
    
    def send(self, message: Message) -> int:
        """Send a message to the appropriate partition"""
        partition_id = self.get_partition(message.key)
        message.topic = self.name
        return self.partitions[partition_id].append(message)
    
    def send_to_partition(
        self,
        partition_id: int,
        message: Message
    ) -> int:
        """Send a message to a specific partition"""
        if partition_id < 0 or partition_id >= self.num_partitions:
            raise ValueError(f"Invalid partition ID: {partition_id}")
        message.topic = self.name
        return self.partitions[partition_id].append(message)
    
    def get_partition_count(self) -> int:
        return self.num_partitions
    
    def get_message_count(self) -> int:
        """Get total message count across all partitions"""
        return sum(len(p) for p in self.partitions)


class MessageQueue:
    """
    In-memory message queue system.
    
    Simulates Kafka's broker functionality with topics and partitions.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern for global message queue"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.topics: Dict[str, Topic] = {}
        self._topic_lock = threading.Lock()
        self._initialized = True
        
        logger.info("Message queue initialized")
    
    def create_topic(
        self,
        name: str,
        num_partitions: int = 8
    ) -> Topic:
        """Create a new topic"""
        with self._topic_lock:
            if name in self.topics:
                return self.topics[name]
            
            topic = Topic(name, num_partitions)
            self.topics[name] = topic
            
            logger.info(
                "Created topic",
                topic=name,
                partitions=num_partitions
            )
            
            return topic
    
    def get_topic(self, name: str) -> Optional[Topic]:
        """Get a topic by name"""
        return self.topics.get(name)
    
    def get_or_create_topic(
        self,
        name: str,
        num_partitions: int = 8
    ) -> Topic:
        """Get existing topic or create new one"""
        topic = self.get_topic(name)
        if topic is None:
            topic = self.create_topic(name, num_partitions)
        return topic
    
    def send(
        self,
        topic_name: str,
        key: str,
        value: Any,
        headers: Optional[Dict[str, str]] = None
    ) -> int:
        """Send a message to a topic"""
        topic = self.get_or_create_topic(topic_name)
        message = Message(
            key=key,
            value=value,
            topic=topic_name,
            headers=headers or {}
        )
        return topic.send(message)
    
    def delete_topic(self, name: str) -> bool:
        """Delete a topic"""
        with self._topic_lock:
            if name in self.topics:
                del self.topics[name]
                logger.info("Deleted topic", topic=name)
                return True
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "topics": {
                name: {
                    "partitions": topic.num_partitions,
                    "messages": topic.get_message_count()
                }
                for name, topic in self.topics.items()
            },
            "total_topics": len(self.topics),
            "total_messages": sum(
                t.get_message_count() for t in self.topics.values()
            )
        }
    
    def clear(self):
        """Clear all topics (for testing)"""
        with self._topic_lock:
            self.topics.clear()
            logger.info("Cleared all topics")


# Global message queue instance
def get_message_queue() -> MessageQueue:
    """Get the global message queue instance"""
    return MessageQueue()
