"""
Git Repository Crawler for Blackbird Search Engine

Crawls Git repositories to extract code files for indexing.
Supports delta-based crawling to only index changed files.
"""

import os
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Iterator, Tuple
from datetime import datetime
import structlog

try:
    from git import Repo, Blob, Tree
    from git.exc import InvalidGitRepositoryError, GitCommandError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    Repo = None

from ..core.document import CodeDocument, detect_language
from ..config import get_config

logger = structlog.get_logger()


@dataclass
class CrawlStats:
    """Statistics from a crawl operation"""
    total_files: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    total_bytes: int = 0
    unique_blobs: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class CrawlResult:
    """Result from crawling a repository"""
    repo_id: str
    repo_path: str
    documents: List[CodeDocument]
    stats: CrawlStats
    parent_repo_id: Optional[str] = None


class GitCrawler:
    """
    Crawls Git repositories to extract code files.
    
    Features:
    - Delta-based crawling (diff against parent repo)
    - File filtering by extension and size
    - Blob deduplication
    - Progress tracking
    """
    
    def __init__(
        self,
        max_file_size_mb: float = 10.0,
        supported_extensions: Optional[List[str]] = None,
        excluded_dirs: Optional[List[str]] = None
    ):
        """
        Initialize the crawler.
        
        Args:
            max_file_size_mb: Maximum file size to index
            supported_extensions: List of file extensions to include
            excluded_dirs: Directories to skip
        """
        if not GIT_AVAILABLE:
            raise ImportError(
                "GitPython is required for Git crawling. "
                "Install with: pip install gitpython"
            )
        
        config = get_config()
        
        self.max_file_size = int(
            (max_file_size_mb or config.MAX_FILE_SIZE_MB) * 1024 * 1024
        )
        self.supported_extensions = set(
            supported_extensions or config.SUPPORTED_EXTENSIONS
        )
        self.excluded_dirs = set(
            excluded_dirs or config.EXCLUDED_DIRS
        )
        
        # Cache of seen blob hashes (for deduplication)
        self._seen_blobs: Set[str] = set()
    
    def crawl_repo(
        self,
        repo_path: str,
        parent_path: Optional[str] = None,
        repo_id: Optional[str] = None
    ) -> CrawlResult:
        """
        Crawl a repository and extract documents.
        
        Args:
            repo_path: Path to the repository
            parent_path: Path to parent repo for delta crawling
            repo_id: Optional repository ID (generated if not provided)
            
        Returns:
            CrawlResult with documents and statistics
        """
        start_time = datetime.utcnow()
        stats = CrawlStats()
        documents = []
        
        try:
            repo = Repo(repo_path)
            
            if not repo_id:
                repo_id = self._generate_repo_id(repo_path)
            
            logger.info(
                "Starting repository crawl",
                repo_id=repo_id,
                path=repo_path,
                has_parent=parent_path is not None
            )
            
            # Get blobs to index
            if parent_path:
                # Delta crawling - only get unique blobs
                parent_repo = Repo(parent_path)
                blobs = self.get_unique_blobs(repo, parent_repo)
                parent_repo_id = self._generate_repo_id(parent_path)
            else:
                # Full crawling
                blobs = self._get_all_blobs(repo)
                parent_repo_id = None
            
            # Process each blob
            for blob_path, blob in blobs:
                stats.total_files += 1
                
                try:
                    doc = self._process_blob(repo_id, blob_path, blob)
                    if doc:
                        documents.append(doc)
                        stats.indexed_files += 1
                        stats.total_bytes += doc.size_bytes
                    else:
                        stats.skipped_files += 1
                except Exception as e:
                    stats.skipped_files += 1
                    stats.errors.append(f"{blob_path}: {str(e)}")
                    logger.warning(
                        "Failed to process blob",
                        path=blob_path,
                        error=str(e)
                    )
            
            stats.unique_blobs = len(self._seen_blobs)
            
        except InvalidGitRepositoryError:
            stats.errors.append(f"Invalid Git repository: {repo_path}")
            logger.error("Invalid Git repository", path=repo_path)
        except Exception as e:
            stats.errors.append(f"Crawl failed: {str(e)}")
            logger.error("Crawl failed", error=str(e))
        
        stats.duration_seconds = (
            datetime.utcnow() - start_time
        ).total_seconds()
        
        logger.info(
            "Repository crawl complete",
            repo_id=repo_id,
            indexed=stats.indexed_files,
            skipped=stats.skipped_files,
            duration=f"{stats.duration_seconds:.2f}s"
        )
        
        return CrawlResult(
            repo_id=repo_id,
            repo_path=repo_path,
            documents=documents,
            stats=stats,
            parent_repo_id=parent_repo_id
        )
    
    def crawl_directory(
        self,
        dir_path: str,
        repo_id: Optional[str] = None
    ) -> CrawlResult:
        """
        Crawl a directory (non-Git) and extract documents.
        
        Useful for indexing arbitrary code directories.
        """
        start_time = datetime.utcnow()
        stats = CrawlStats()
        documents = []
        
        dir_path = Path(dir_path)
        
        if not repo_id:
            repo_id = self._generate_repo_id(str(dir_path))
        
        logger.info(
            "Starting directory crawl",
            repo_id=repo_id,
            path=str(dir_path)
        )
        
        for file_path in self._walk_directory(dir_path):
            stats.total_files += 1
            
            try:
                relative_path = str(file_path.relative_to(dir_path))
                
                # Check file size
                file_size = file_path.stat().st_size
                if file_size > self.max_file_size:
                    stats.skipped_files += 1
                    continue
                
                # Check extension
                if not self._should_index_file(file_path.name):
                    stats.skipped_files += 1
                    continue
                
                # Read content
                try:
                    content = file_path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    # Try with latin-1 fallback
                    try:
                        content = file_path.read_text(encoding='latin-1')
                    except Exception:
                        stats.skipped_files += 1
                        continue
                
                # Create document
                doc = CodeDocument.create(
                    repo_id=repo_id,
                    path=relative_path,
                    content=content,
                    language=detect_language(relative_path)
                )
                
                documents.append(doc)
                stats.indexed_files += 1
                stats.total_bytes += doc.size_bytes
                
            except Exception as e:
                stats.skipped_files += 1
                stats.errors.append(f"{file_path}: {str(e)}")
        
        stats.duration_seconds = (
            datetime.utcnow() - start_time
        ).total_seconds()
        
        logger.info(
            "Directory crawl complete",
            repo_id=repo_id,
            indexed=stats.indexed_files,
            skipped=stats.skipped_files,
            duration=f"{stats.duration_seconds:.2f}s"
        )
        
        return CrawlResult(
            repo_id=repo_id,
            repo_path=str(dir_path),
            documents=documents,
            stats=stats
        )
    
    def get_unique_blobs(
        self,
        repo: "Repo",
        parent_repo: "Repo"
    ) -> List[Tuple[str, "Blob"]]:
        """
        Get blobs unique to this repo (not in parent).
        
        This is the core of delta-based crawling. By diffing
        against a parent repository, we avoid re-indexing
        shared content (e.g., for forks).
        """
        # Get all blob hashes from parent
        parent_hashes = set()
        for item in parent_repo.tree().traverse():
            if item.type == 'blob':
                parent_hashes.add(item.hexsha)
        
        # Get unique blobs from current repo
        unique_blobs = []
        for blob_path, blob in self._get_all_blobs(repo):
            if blob.hexsha not in parent_hashes:
                unique_blobs.append((blob_path, blob))
        
        logger.info(
            "Delta crawl stats",
            parent_blobs=len(parent_hashes),
            unique_blobs=len(unique_blobs)
        )
        
        return unique_blobs
    
    def _get_all_blobs(self, repo: "Repo") -> Iterator[Tuple[str, "Blob"]]:
        """
        Get all blobs from the repository's HEAD.
        """
        try:
            tree = repo.head.commit.tree
        except Exception:
            # Empty or invalid repo
            return
        
        for item in tree.traverse():
            if item.type == 'blob':
                # Get full path
                blob_path = item.path
                
                # Check if in excluded directory
                if self._is_excluded_path(blob_path):
                    continue
                
                yield blob_path, item
    
    def _process_blob(
        self,
        repo_id: str,
        blob_path: str,
        blob: "Blob"
    ) -> Optional[CodeDocument]:
        """
        Process a Git blob and create a document.
        """
        # Check extension
        if not self._should_index_file(blob_path):
            return None
        
        # Check size
        if blob.size > self.max_file_size:
            return None
        
        # Check for duplicate blob
        if blob.hexsha in self._seen_blobs:
            return None
        
        # Read content
        try:
            content = blob.data_stream.read().decode('utf-8')
        except UnicodeDecodeError:
            try:
                content = blob.data_stream.read().decode('latin-1')
            except Exception:
                return None
        
        self._seen_blobs.add(blob.hexsha)
        
        # Create document
        return CodeDocument.create(
            repo_id=repo_id,
            path=blob_path,
            content=content,
            language=detect_language(blob_path)
        )
    
    def _should_index_file(self, filename: str) -> bool:
        """Check if file should be indexed based on extension"""
        _, ext = os.path.splitext(filename.lower())
        return ext in self.supported_extensions
    
    def _is_excluded_path(self, path: str) -> bool:
        """Check if path is in an excluded directory"""
        parts = Path(path).parts
        return any(part in self.excluded_dirs for part in parts)
    
    def _walk_directory(self, dir_path: Path) -> Iterator[Path]:
        """Walk directory recursively, skipping excluded dirs"""
        for item in dir_path.iterdir():
            if item.is_dir():
                if item.name not in self.excluded_dirs:
                    yield from self._walk_directory(item)
            elif item.is_file():
                yield item
    
    def _generate_repo_id(self, repo_path: str) -> str:
        """Generate a unique repository ID"""
        return hashlib.sha256(
            repo_path.encode()
        ).hexdigest()[:12]
    
    def clear_cache(self):
        """Clear the seen blobs cache"""
        self._seen_blobs.clear()


class IncrementalCrawler(GitCrawler):
    """
    Crawler that tracks changes incrementally.
    
    Uses Git commit history to detect and index only
    changed files since the last crawl.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mapping of repo_id to last indexed commit
        self._last_commits: Dict[str, str] = {}
    
    def crawl_changes(
        self,
        repo_path: str,
        repo_id: Optional[str] = None
    ) -> CrawlResult:
        """
        Crawl only files changed since last crawl.
        """
        repo = Repo(repo_path)
        
        if not repo_id:
            repo_id = self._generate_repo_id(repo_path)
        
        current_commit = repo.head.commit.hexsha
        last_commit = self._last_commits.get(repo_id)
        
        if not last_commit:
            # First crawl - index everything
            result = self.crawl_repo(repo_path, repo_id=repo_id)
        else:
            # Get changed files
            result = self._crawl_diff(
                repo, repo_id, last_commit, current_commit
            )
        
        # Update last commit
        self._last_commits[repo_id] = current_commit
        
        return result
    
    def _crawl_diff(
        self,
        repo: "Repo",
        repo_id: str,
        from_commit: str,
        to_commit: str
    ) -> CrawlResult:
        """Crawl files changed between commits"""
        stats = CrawlStats()
        documents = []
        
        try:
            diffs = repo.commit(from_commit).diff(to_commit)
            
            for diff in diffs:
                if diff.b_blob:  # File was added or modified
                    try:
                        doc = self._process_blob(
                            repo_id,
                            diff.b_path,
                            diff.b_blob
                        )
                        if doc:
                            documents.append(doc)
                            stats.indexed_files += 1
                    except Exception as e:
                        stats.errors.append(str(e))
                
                stats.total_files += 1
        except Exception as e:
            stats.errors.append(f"Diff failed: {str(e)}")
        
        return CrawlResult(
            repo_id=repo_id,
            repo_path=repo.working_dir,
            documents=documents,
            stats=stats
        )
