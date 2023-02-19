"""
Blackbird Search Engine Configuration
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """Main configuration for Blackbird Search Engine"""
    
    # Ngram Settings
    NGRAM_SIZE: int = 3  # Trigrams by default
    MIN_NGRAM_SIZE: int = 2
    MAX_NGRAM_SIZE: int = 5
    
    # Sharding
    NUM_SHARDS: int = 8
    SHARD_REPLICATION_FACTOR: int = 1
    
    # Index Settings
    INDEX_PATH: Path = field(default_factory=lambda: Path("./data/index"))
    COMPACTION_THRESHOLD: int = 100  # Number of segments before compaction
    COMPACTION_INTERVAL_SECONDS: int = 3600  # 1 hour for incremental
    MAX_SEGMENT_SIZE_MB: int = 256
    
    # Kafka Settings (simulated in-memory by default)
    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_REPO_EVENTS_TOPIC: str = "repo-events"
    KAFKA_DOCUMENTS_TOPIC: str = "documents"
    KAFKA_CONSUMER_GROUP: str = "blackbird-indexer"
    
    # Crawler Settings
    MAX_FILE_SIZE_MB: int = 10  # Skip files larger than this
    SUPPORTED_EXTENSIONS: List[str] = field(default_factory=lambda: [
        ".py", ".js", ".ts", ".jsx", ".tsx",
        ".java", ".kt", ".scala",
        ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp",
        ".rb", ".php",
        ".cs", ".fs",
        ".swift", ".m",
        ".sql", ".sh", ".bash",
        ".yaml", ".yml", ".json", ".xml",
        ".md", ".txt", ".rst",
        ".html", ".css", ".scss", ".less"
    ])
    EXCLUDED_DIRS: List[str] = field(default_factory=lambda: [
        "node_modules", "venv", ".venv", "__pycache__",
        ".git", ".svn", ".hg",
        "vendor", "dist", "build", "target",
        ".idea", ".vscode"
    ])
    
    # MinHash Settings for Similarity
    MINHASH_NUM_PERM: int = 128  # Number of permutations
    SIMILARITY_THRESHOLD: float = 0.5  # Jaccard similarity threshold
    
    # Search Settings
    MAX_RESULTS: int = 100
    DEFAULT_RESULTS: int = 20
    SEARCH_TIMEOUT_SECONDS: int = 30
    SYMBOL_BOOST_FACTOR: float = 2.0  # Boost for symbol matches
    
    # API Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4
    CORS_ORIGINS: List[str] = field(default_factory=lambda: ["*"])
    
    # Database
    DATABASE_PATH: Path = field(default_factory=lambda: Path("./data/blackbird.db"))
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    def __post_init__(self):
        """Create necessary directories"""
        self.INDEX_PATH.mkdir(parents=True, exist_ok=True)
        self.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()


def get_config() -> Config:
    """Get the global configuration instance"""
    return config


def update_config(**kwargs) -> Config:
    """Update configuration values"""
    global config
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    return config
