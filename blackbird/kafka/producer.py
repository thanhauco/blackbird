"""
Event Producer for Blackbird Search Engine

Publishes events to Kafka topics for repository changes and documents.
"""

from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import structlog

from .queue import MessageQueue, Message, get_message_queue
from ..core.document import CodeDocument
from ..config import get_config

logger = structlog.get_logger()


class EventType(Enum):
    """Types of events that can be published"""
    REPO_CREATED = "repo_created"
    REPO_UPDATED = "repo_updated"
    REPO_DELETED = "repo_deleted"
    COMMIT_PUSHED = "commit_pushed"
    BRANCH_CREATED = "branch_created"
    BRANCH_DELETED = "branch_deleted"


@dataclass
class RepoChangeEvent:
    """
    Event representing a repository change.
    
    Published when repositories are created, updated, or deleted.
    """
    repo_id: str
    repo_path: str
    event_type: EventType
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "repo_path": self.repo_path,
            "event_type": self.event_type.value,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoChangeEvent":
        return cls(
            repo_id=data["repo_id"],
            repo_path=data["repo_path"],
            event_type=EventType(data["event_type"]),
            commit_sha=data.get("commit_sha"),
            branch=data.get("branch"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {})
        )


@dataclass
class DocumentEvent:
    """
    Event representing a document to be indexed.
    
    Published after crawling, consumed by indexer shards.
    """
    document: CodeDocument
    shard_id: int
    action: str = "index"  # index, update, delete
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "shard_id": self.shard_id,
            "action": self.action,
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentEvent":
        return cls(
            document=CodeDocument.from_dict(data["document"]),
            shard_id=data["shard_id"],
            action=data.get("action", "index"),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


class EventProducer:
    """
    Produces events to Kafka topics.
    
    Handles publishing repository change events and document events
    for processing by crawlers and indexers.
    """
    
    def __init__(
        self,
        num_shards: int = 8,
        repo_events_topic: Optional[str] = None,
        documents_topic: Optional[str] = None
    ):
        """
        Initialize the event producer.
        
        Args:
            num_shards: Number of indexer shards for partitioning
            repo_events_topic: Topic name for repo change events
            documents_topic: Topic name for document events
        """
        config = get_config()
        
        self.num_shards = num_shards or config.NUM_SHARDS
        self.repo_events_topic = repo_events_topic or config.KAFKA_REPO_EVENTS_TOPIC
        self.documents_topic = documents_topic or config.KAFKA_DOCUMENTS_TOPIC
        
        self.queue = get_message_queue()
        
        # Create topics
        self.queue.create_topic(self.repo_events_topic, num_partitions=4)
        self.queue.create_topic(self.documents_topic, num_partitions=self.num_shards)
        
        # Statistics
        self._events_published = 0
        self._documents_published = 0
        
        logger.info(
            "Event producer initialized",
            repo_topic=self.repo_events_topic,
            doc_topic=self.documents_topic,
            shards=self.num_shards
        )
    
    def publish_repo_change(
        self,
        repo_id: str,
        repo_path: str,
        event_type: EventType,
        commit_sha: Optional[str] = None,
        branch: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Publish a repository change event.
        
        Returns:
            Message offset
        """
        event = RepoChangeEvent(
            repo_id=repo_id,
            repo_path=repo_path,
            event_type=event_type,
            commit_sha=commit_sha,
            branch=branch,
            metadata=metadata or {}
        )
        
        offset = self.queue.send(
            topic_name=self.repo_events_topic,
            key=repo_id,
            value=event.to_dict()
        )
        
        self._events_published += 1
        
        logger.debug(
            "Published repo change event",
            repo_id=repo_id,
            event_type=event_type.value,
            offset=offset
        )
        
        return offset
    
    def publish_document(
        self,
        document: CodeDocument,
        action: str = "index"
    ) -> int:
        """
        Publish a document for indexing.
        
        The document is routed to the appropriate shard based on
        its ID (consistent hashing).
        
        Returns:
            Message offset
        """
        # Determine shard ID from document ID
        shard_id = hash(document.id) % self.num_shards
        
        event = DocumentEvent(
            document=document,
            shard_id=shard_id,
            action=action
        )
        
        # Send to the shard's partition
        topic = self.queue.get_topic(self.documents_topic)
        message = Message(
            key=document.id,
            value=event.to_dict(),
            topic=self.documents_topic
        )
        offset = topic.send_to_partition(shard_id, message)
        
        self._documents_published += 1
        
        logger.debug(
            "Published document event",
            doc_id=document.id,
            shard_id=shard_id,
            action=action,
            offset=offset
        )
        
        return offset
    
    def publish_documents(
        self,
        documents: List[CodeDocument],
        action: str = "index"
    ) -> List[int]:
        """
        Publish multiple documents.
        
        Returns:
            List of message offsets
        """
        offsets = []
        for doc in documents:
            offset = self.publish_document(doc, action)
            offsets.append(offset)
        
        logger.info(
            "Published document batch",
            count=len(documents),
            action=action
        )
        
        return offsets
    
    def publish_deletion(self, doc_id: str, repo_id: str) -> int:
        """
        Publish a document deletion event.
        """
        # Create a minimal document for the deletion event
        document = CodeDocument(
            id=doc_id,
            repo_id=repo_id,
            path="",
            content="",
            language="",
            blob_hash=""
        )
        
        return self.publish_document(document, action="delete")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get producer statistics"""
        return {
            "events_published": self._events_published,
            "documents_published": self._documents_published,
            "queue_stats": self.queue.get_stats()
        }
    
    def flush(self):
        """
        Flush pending messages.
        
        In the in-memory implementation, this is a no-op since
        messages are immediately available.
        """
        pass
