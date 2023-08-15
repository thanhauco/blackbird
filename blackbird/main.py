"""
Blackbird Search Engine - Main Entry Point

A high-performance code search engine inspired by GitHub's Blackbird.
"""

import argparse
import sys
from pathlib import Path

import structlog
import uvicorn

from .config import get_config, update_config

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def main():
    """Main entry point for the Blackbird search engine."""
    parser = argparse.ArgumentParser(
        description="Blackbird - A high-performance code search engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start the server
  python -m blackbird

  # Start with custom port
  python -m blackbird --port 9000

  # Index a repository
  python -m blackbird index /path/to/repo

  # Search from command line
  python -m blackbird search "onClick"
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Server command (default)
    server_parser = subparsers.add_parser("serve", help="Start the search server")
    server_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    server_parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    
    # Index command
    index_parser = subparsers.add_parser("index", help="Index a repository")
    index_parser.add_argument("path", help="Path to repository or directory")
    index_parser.add_argument("--id", help="Repository ID")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search from command line")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=10, help="Max results")
    search_parser.add_argument("--language", help="Filter by language")
    
    # Stats command
    subparsers.add_parser("stats", help="Show index statistics")
    
    args = parser.parse_args()
    
    # Default to serve command
    if args.command is None:
        args.command = "serve"
        args.host = "0.0.0.0"
        args.port = 8000
        args.reload = False
        args.workers = 1
    
    if args.command == "serve":
        run_server(args)
    elif args.command == "index":
        run_index(args)
    elif args.command == "search":
        run_search(args)
    elif args.command == "stats":
        run_stats(args)


def run_server(args):
    """Start the FastAPI server."""
    logger.info(
        "Starting Blackbird server",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
    
    uvicorn.run(
        "blackbird.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1
    )


def run_index(args):
    """Index a repository from command line."""
    from .crawler.git_crawler import GitCrawler
    from .shard.manager import ShardManager
    
    config = get_config()
    
    path = Path(args.path)
    if not path.exists():
        logger.error("Path not found", path=str(path))
        sys.exit(1)
    
    logger.info("Initializing indexer...")
    
    shard_manager = ShardManager(
        num_shards=config.NUM_SHARDS,
        index_path=config.INDEX_PATH,
        ngram_size=config.NGRAM_SIZE
    )
    
    crawler = GitCrawler()
    
    logger.info("Crawling repository...", path=str(path))
    
    if path.is_dir() and (path / ".git").exists():
        result = crawler.crawl_repo(str(path), repo_id=args.id)
    else:
        result = crawler.crawl_directory(str(path), repo_id=args.id)
    
    logger.info(
        "Crawl complete",
        files=result.stats.total_files,
        indexed=result.stats.indexed_files,
        skipped=result.stats.skipped_files
    )
    
    logger.info("Indexing documents...")
    indexed = shard_manager.index_documents(result.documents)
    
    logger.info("Saving index...")
    shard_manager.save_all()
    
    logger.info(
        "Indexing complete",
        repo_id=result.repo_id,
        documents_indexed=indexed,
        duration=f"{result.stats.duration_seconds:.2f}s"
    )


def run_search(args):
    """Search from command line."""
    from .shard.manager import ShardManager
    from .api.search import SearchService
    
    config = get_config()
    
    logger.info("Loading index...")
    
    shard_manager = ShardManager(
        num_shards=config.NUM_SHARDS,
        index_path=config.INDEX_PATH,
        ngram_size=config.NGRAM_SIZE
    )
    
    try:
        shard_manager.load_all()
    except Exception as e:
        logger.error("Failed to load index", error=str(e))
        sys.exit(1)
    
    search_service = SearchService(shard_manager)
    
    logger.info("Searching...", query=args.query)
    
    response = search_service.search(
        query=args.query,
        limit=args.limit,
        language=args.language
    )
    
    print(f"\n{'='*60}")
    print(f"Query: {response.query}")
    print(f"Results: {response.total_results} ({response.took_ms:.1f}ms)")
    print(f"{'='*60}\n")
    
    for i, result in enumerate(response.results, 1):
        print(f"{i}. {result.path}")
        print(f"   Score: {result.score:.2f} | Language: {result.language}")
        if result.has_symbol_match:
            print(f"   ✓ Symbol match")
        print()


def run_stats(args):
    """Show index statistics."""
    from .shard.manager import ShardManager
    
    config = get_config()
    
    shard_manager = ShardManager(
        num_shards=config.NUM_SHARDS,
        index_path=config.INDEX_PATH,
        ngram_size=config.NGRAM_SIZE
    )
    
    try:
        shard_manager.load_all()
    except Exception:
        pass
    
    stats = shard_manager.get_stats()
    
    print(f"\n{'='*60}")
    print("BLACKBIRD INDEX STATISTICS")
    print(f"{'='*60}\n")
    
    print(f"Shards:          {stats['num_shards']}")
    print(f"Total Documents: {stats['total_documents']:,}")
    print(f"Total Ngrams:    {stats['total_ngrams']:,}")
    print(f"Total Segments:  {stats['total_segments']}")
    
    print(f"\n{'Shard Details':^60}")
    print("-" * 60)
    print(f"{'ID':<8} {'Documents':<12} {'Ngrams':<12} {'Segments':<10}")
    print("-" * 60)
    
    for shard in stats['shards']:
        print(f"{shard['shard_id']:<8} {shard['documents']:<12,} {shard['ngrams']:<12,} {shard['segments']:<10}")
    
    print()


if __name__ == "__main__":
    main()
