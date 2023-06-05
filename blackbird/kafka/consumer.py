"""
Event Consumer for Blackbird Search Engine

Consumes events from Kafka topics for processing by crawlers and indexers.
"""

import time
import threading
from typing import Dict, Optional, Any, List, Iterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
import structlog

from .queue import MessageQueue, Message, Topic, get_message_queue
from .producer import RepoChangeEvent, DocumentEvent
from ..config import get_config

logger = structlog.get_logger()


@dataclass
class ConsumerOffset:
    """
    Tracks consumer offset for a partition.
    """
    topic: str
    partition: int
    offset: int = 0
    
    def advance(self, new_offset: int):
        """Advance the offset"""
        if new_offset > self.offset:
            self.offset = new_offset


class ShardConsumer:
    """
    Consumes documents for a specific indexer shard.
    
    Each shard consumes exactly one partition from the documents
    topic, ensuring ordered processing for query consistency.
    """
    
    def __init__(
        self,
        shard_id: int,
        topic_name: Optional[str] = None,
        poll_interval: float = 0.1
    ):
        """
        Initialize the shard consumer.
        
        Args:
            shard_id: ID of the shard (matches partition ID)
            topic_name: Topic to consume from
            poll_interval: Seconds between polls when no messages
        """
        config = get_config()
        
        self.shard_id = shard_id
        self.topic_name = topic_name or config.KAFKA_DOCUMENTS_TOPIC
        self.poll_interval = poll_interval
        
        self.queue = get_message_queue()
        self.offset = ConsumerOffset(
            topic=self.topic_name,
            partition=shard_id
        )
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        logger.info(
            "Shard consumer initialized",
            shard_id=shard_id,
            topic=self.topic_name
        )
    
    def consume(self, max_messages: int = 100) -> List[DocumentEvent]:
        """
        Consume messages from the partition.
        
        Returns:
            List of DocumentEvent objects
        """
        topic = self.queue.get_topic(self.topic_name)
        if not topic:
            return []
        
        partition = topic.partitions[self.shard_id]
        messages = partition.get_range(self.offset.offset, max_messages)
        
        events = []
        for msg in messages:
            try:
                event = DocumentEvent.from_dict(msg.value)
                events.append(event)
                self.offset.advance(msg.offset + 1)
            except Exception as e:
                logger.error(
                    "Failed to parse message",
                    offset=msg.offset,
                    error=str(e)
                )
        
        return events
    
    def consume_one(self) -> Optional[DocumentEvent]:
        """Consume a single message"""
        events = self.consume(max_messages=1)
        return events[0] if events else None
    
    def poll(
        self,
        timeout: float = 1.0,
        max_messages: int = 100
    ) -> List[DocumentEvent]:
        """
        Poll for messages with timeout.
        
        Waits up to timeout seconds for messages to arrive.
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            events = self.consume(max_messages)
            if events:
                return events
            time.sleep(self.poll_interval)
        
        return []
    
    def iter_messages(self) -> Iterator[DocumentEvent]:
        """
        Iterate over messages continuously.
        
        This is a blocking iterator that yields messages as they arrive.
        """
        while True:
            events = self.poll(timeout=1.0)
            for event in events:
                yield event
    
    def start_async(
        self,
        handler: Callable[[DocumentEvent], None]
    ):
        """
        Start consuming messages asynchronously.
        
        Args:
            handler: Callback function to process each event
        """
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._consume_loop,
            args=(handler,),
            daemon=True
        )
        self._thread.start()
        
        logger.info(
            "Started async consumer",
            shard_id=self.shard_id
        )
    
    def stop_async(self):
        """Stop async consumption"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        
        logger.info(
            "Stopped async consumer",
            shard_id=self.shard_id
        )
    
    def _consume_loop(self, handler: Callable[[DocumentEvent], None]):
        """Internal consumption loop"""
        while self._running:
            try:
                events = self.poll(timeout=1.0)
                for event in events:
                    handler(event)
            except Exception as e:
                logger.error(
                    "Error in consume loop",
                    shard_id=self.shard_id,
                    error=str(e)
                )
    
    def commit(self):
        """
        Commit current offset.
        
        In the in-memory implementation, offsets are tracked
        automatically, so this is a no-op.
        """
        pass
    
    def get_lag(self) -> int:
        """Get number of unconsumed messages"""
        topic = self.queue.get_topic(self.topic_name)
        if not topic:
            return 0
        
        partition = topic.partitions[self.shard_id]
        return len(partition) - self.offset.offset


class RepoEventConsumer:
    """
    Consumes repository change events.
    
    Used by crawlers to detect when repositories need to be re-indexed.
    """
    
    def __init__(
        self,
        topic_name: Optional[str] = None,
        consumer_group: Optional[str] = None
    ):
        """
        Initialize the repo event consumer.
        """
        config = get_config()
        
        self.topic_name = topic_name or config.KAFKA_REPO_EVENTS_TOPIC
        self.consumer_group = consumer_group or config.KAFKA_CONSUMER_GROUP
        
        self.queue = get_message_queue()
        self.offsets: Dict[int, ConsumerOffset] = {}
        
        logger.info(
            "Repo event consumer initialized",
            topic=self.topic_name,
            group=self.consumer_group
        )
    
    def consume(self, max_messages: int = 100) -> List[RepoChangeEvent]:
        """
        Consume repo change events from all partitions.
        """
        topic = self.queue.get_topic(self.topic_name)
        if not topic:
            return []
        
        events = []
        
        for partition in topic.partitions:
            # Get or create offset tracker
            if partition.partition_id not in self.offsets:
                self.offsets[partition.partition_id] = ConsumerOffset(
                    topic=self.topic_name,
                    partition=partition.partition_id
                )
            
            offset = self.offsets[partition.partition_id]
            messages = partition.get_range(offset.offset, max_messages)
            
            for msg in messages:
                try:
                    event = RepoChangeEvent.from_dict(msg.value)
                    events.append(event)
                    offset.advance(msg.offset + 1)
                except Exception as e:
                    logger.error(
                        "Failed to parse repo event",
                        offset=msg.offset,
                        error=str(e)
                    )
        
        return events
    
    def poll(
        self,
        timeout: float = 1.0,
        max_messages: int = 100
    ) -> List[RepoChangeEvent]:
        """Poll for events with timeout"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            events = self.consume(max_messages)
            if events:
                return events
            time.sleep(0.1)
        
        return []


class ConsumerGroup:
    """
    Manages a group of shard consumers.
    
    Coordinates consumption across all shards and provides
    aggregate statistics.
    """
    
    def __init__(
        self,
        num_shards: int = 8,
        topic_name: Optional[str] = None
    ):
        """
        Initialize the consumer group.
        """
        config = get_config()
        
        self.num_shards = num_shards or config.NUM_SHARDS
        self.topic_name = topic_name or config.KAFKA_DOCUMENTS_TOPIC
        
        self.consumers = [
            ShardConsumer(shard_id=i, topic_name=self.topic_name)
            for i in range(self.num_shards)
        ]
        
        logger.info(
            "Consumer group initialized",
            shards=self.num_shards
        )
    
    def get_consumer(self, shard_id: int) -> ShardConsumer:
        """Get consumer for a specific shard"""
        return self.consumers[shard_id]
    
    def consume_all(self, max_per_shard: int = 100) -> Dict[int, List[DocumentEvent]]:
        """
        Consume from all shards.
        
        Returns:
            Dict mapping shard_id to list of events
        """
        results = {}
        for consumer in self.consumers:
            events = consumer.consume(max_per_shard)
            if events:
                results[consumer.shard_id] = events
        return results
    
    def get_total_lag(self) -> int:
        """Get total lag across all shards"""
        return sum(c.get_lag() for c in self.consumers)
    
    def start_all_async(
        self,
        handler: Callable[[int, DocumentEvent], None]
    ):
        """
        Start all consumers asynchronously.
        
        Args:
            handler: Callback(shard_id, event) for each event
        """
        for consumer in self.consumers:
            # Wrap handler to include shard_id
            shard_handler = lambda e, sid=consumer.shard_id: handler(sid, e)
            consumer.start_async(shard_handler)
    
    def stop_all_async(self):
        """Stop all async consumers"""
        for consumer in self.consumers:
            consumer.stop_async()
