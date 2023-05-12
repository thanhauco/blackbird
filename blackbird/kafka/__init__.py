"""
Blackbird Kafka Module (In-Memory Simulation)

Provides Kafka-like event streaming for the search engine.
Uses an in-memory implementation by default, with optional real Kafka support.
"""

from .producer import EventProducer, RepoChangeEvent, DocumentEvent
from .consumer import ShardConsumer, ConsumerGroup
from .queue import MessageQueue, Message, Topic

__all__ = [
    "EventProducer",
    "RepoChangeEvent",
    "DocumentEvent",
    "ShardConsumer",
    "ConsumerGroup",
    "MessageQueue",
    "Message",
    "Topic"
]
