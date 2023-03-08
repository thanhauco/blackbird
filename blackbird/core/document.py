"""
Document Model for Blackbird Search Engine

Defines the structure for code documents, symbols, and metadata.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import hashlib
import json


class SymbolType(Enum):
    """Types of code symbols that can be extracted"""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    ENUM = "enum"
    MODULE = "module"
    IMPORT = "import"
    TYPE = "type"
    PROPERTY = "property"
    PARAMETER = "parameter"
    UNKNOWN = "unknown"


@dataclass
class Symbol:
    """
    Represents a code symbol (function, class, variable, etc.)
    
    Symbols are extracted from code and indexed separately for
    boosted search relevance.
    """
    name: str
    symbol_type: SymbolType
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    parent: Optional[str] = None  # Parent symbol (e.g., class for method)
    signature: Optional[str] = None  # Full signature for functions
    documentation: Optional[str] = None  # Docstring/comment
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.symbol_type.value,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "column_start": self.column_start,
            "column_end": self.column_end,
            "parent": self.parent,
            "signature": self.signature,
            "documentation": self.documentation
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Symbol":
        return cls(
            name=data["name"],
            symbol_type=SymbolType(data["type"]),
            line_start=data["line_start"],
            line_end=data["line_end"],
            column_start=data.get("column_start", 0),
            column_end=data.get("column_end", 0),
            parent=data.get("parent"),
            signature=data.get("signature"),
            documentation=data.get("documentation")
        )


@dataclass
class CodeDocument:
    """
    Represents a code file/blob for indexing.
    
    This is the primary unit of indexing in Blackbird.
    Each document corresponds to a file in a repository.
    """
    id: str  # Unique document ID
    repo_id: str  # Repository identifier
    path: str  # File path within repository
    content: str  # File content
    language: str  # Programming language
    blob_hash: str  # Git blob hash for deduplication
    
    # Metadata
    symbols: List[Symbol] = field(default_factory=list)
    score: float = 1.0  # Base relevance score
    size_bytes: int = 0
    line_count: int = 0
    
    # Timestamps
    indexed_at: datetime = field(default_factory=datetime.utcnow)
    modified_at: Optional[datetime] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate derived fields"""
        if not self.size_bytes:
            self.size_bytes = len(self.content.encode('utf-8'))
        if not self.line_count:
            self.line_count = self.content.count('\n') + 1
    
    @classmethod
    def create(
        cls,
        repo_id: str,
        path: str,
        content: str,
        language: str = "unknown"
    ) -> "CodeDocument":
        """
        Factory method to create a document with auto-generated ID and hash.
        """
        # Generate blob hash (similar to Git)
        blob_hash = cls._compute_blob_hash(content)
        
        # Generate document ID from repo + path + hash
        doc_id = cls._generate_id(repo_id, path, blob_hash)
        
        return cls(
            id=doc_id,
            repo_id=repo_id,
            path=path,
            content=content,
            language=language,
            blob_hash=blob_hash
        )
    
    @staticmethod
    def _compute_blob_hash(content: str) -> str:
        """Compute Git-style blob hash"""
        data = content.encode('utf-8')
        header = f"blob {len(data)}\0".encode('utf-8')
        return hashlib.sha1(header + data).hexdigest()
    
    @staticmethod
    def _generate_id(repo_id: str, path: str, blob_hash: str) -> str:
        """Generate unique document ID"""
        combined = f"{repo_id}:{path}:{blob_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def get_symbol_names(self) -> List[str]:
        """Get list of all symbol names in document"""
        return [s.name for s in self.symbols]
    
    def get_symbols_by_type(self, symbol_type: SymbolType) -> List[Symbol]:
        """Get symbols of a specific type"""
        return [s for s in self.symbols if s.symbol_type == symbol_type]
    
    def get_functions(self) -> List[Symbol]:
        """Get all function/method symbols"""
        return [
            s for s in self.symbols 
            if s.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD)
        ]
    
    def get_classes(self) -> List[Symbol]:
        """Get all class symbols"""
        return self.get_symbols_by_type(SymbolType.CLASS)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "path": self.path,
            "content": self.content,
            "language": self.language,
            "blob_hash": self.blob_hash,
            "symbols": [s.to_dict() for s in self.symbols],
            "score": self.score,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "indexed_at": self.indexed_at.isoformat(),
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeDocument":
        """Deserialize from dictionary"""
        doc = cls(
            id=data["id"],
            repo_id=data["repo_id"],
            path=data["path"],
            content=data["content"],
            language=data["language"],
            blob_hash=data["blob_hash"],
            symbols=[Symbol.from_dict(s) for s in data.get("symbols", [])],
            score=data.get("score", 1.0),
            size_bytes=data.get("size_bytes", 0),
            line_count=data.get("line_count", 0),
            metadata=data.get("metadata", {})
        )
        
        if data.get("indexed_at"):
            doc.indexed_at = datetime.fromisoformat(data["indexed_at"])
        if data.get("modified_at"):
            doc.modified_at = datetime.fromisoformat(data["modified_at"])
        
        return doc
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "CodeDocument":
        """Deserialize from JSON string"""
        return cls.from_dict(json.loads(json_str))


@dataclass
class DocumentBatch:
    """
    A batch of documents for bulk indexing.
    """
    documents: List[CodeDocument]
    batch_id: str = ""
    shard_id: int = -1
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if not self.batch_id:
            self.batch_id = hashlib.md5(
                str(self.created_at.timestamp()).encode()
            ).hexdigest()[:8]
    
    def __len__(self) -> int:
        return len(self.documents)
    
    def __iter__(self):
        return iter(self.documents)
    
    def total_size(self) -> int:
        """Total size of all documents in bytes"""
        return sum(doc.size_bytes for doc in self.documents)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "shard_id": self.shard_id,
            "created_at": self.created_at.isoformat(),
            "document_count": len(self.documents),
            "documents": [doc.to_dict() for doc in self.documents]
        }


# Language detection mapping
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    ".r": "r",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".hs": "haskell",
    ".lhs": "haskell",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
}


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension"""
    import os
    _, ext = os.path.splitext(file_path.lower())
    return EXTENSION_TO_LANGUAGE.get(ext, "unknown")
