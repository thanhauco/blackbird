"""
Extended API Routes for ML Features

Adds semantic search, code intelligence, AI assistant, and analysis endpoints.
"""

from typing import List, Dict, Optional, Any
from fastapi import APIRouter, Query, HTTPException, Body
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/v2", tags=["ML Features"])


# Request/Response Models

class SemanticSearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(20, ge=1, le=100)
    mode: str = Field("hybrid", description="Search mode: ngram, semantic, or hybrid")
    language: Optional[str] = None
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class SemanticSearchResult(BaseModel):
    doc_id: str
    path: str
    repo_id: str
    language: str
    ngram_score: float
    semantic_score: float
    combined_score: float
    snippet: str = ""


class CodeIntelRequest(BaseModel):
    file_path: str
    line: int
    column: int
    action: str = Field(..., description="Action: definition, references, hover, completions")
    word: Optional[str] = None


class AIQueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    code_context: Optional[str] = None
    language: str = "python"
    action: str = Field("chat", description="Action: chat, explain, generate, review, search")


class AnalysisRequest(BaseModel):
    file_path: str
    content: str
    language: str = "python"


# Service references (set by main app)
_semantic_engine = None
_code_intel = None
_ai_assistant = None
_quality_analyzer = None


def set_ml_services(semantic=None, intel=None, ai=None, analyzer=None):
    """Set service references"""
    global _semantic_engine, _code_intel, _ai_assistant, _quality_analyzer
    _semantic_engine = semantic
    _code_intel = intel
    _ai_assistant = ai
    _quality_analyzer = analyzer


# Semantic Search Endpoints

@router.post("/search/semantic", response_model=List[SemanticSearchResult])
async def semantic_search(request: SemanticSearchRequest):
    """
    Perform semantic code search using neural embeddings.
    
    Supports three modes:
    - ngram: Traditional trigram-based search
    - semantic: Neural embedding similarity search
    - hybrid: Combined search with RRF fusion
    """
    if not _semantic_engine:
        raise HTTPException(503, "Semantic search not initialized")
    
    from ..ml.hybrid import SearchMode
    
    mode_map = {
        "ngram": SearchMode.NGRAM,
        "semantic": SearchMode.SEMANTIC,
        "hybrid": SearchMode.HYBRID
    }
    
    search_mode = mode_map.get(request.mode, SearchMode.HYBRID)
    
    results = _semantic_engine.search(
        query=request.query,
        mode=search_mode,
        limit=request.limit,
        min_score=request.min_score,
        language=request.language
    )
    
    return [
        SemanticSearchResult(
            doc_id=r.doc_id,
            path=r.path,
            repo_id=r.repo_id,
            language=r.language,
            ngram_score=r.ngram_score,
            semantic_score=r.semantic_score,
            combined_score=r.combined_score,
            snippet=r.snippet
        )
        for r in results
    ]


@router.post("/search/natural")
async def natural_language_search(query: str = Body(..., embed=True)):
    """
    Convert natural language to code search.
    
    Uses AI to understand intent and generate search terms.
    """
    if not _ai_assistant:
        raise HTTPException(503, "AI assistant not initialized")
    
    result = _ai_assistant.natural_language_search(query)
    
    return {
        "original_query": query,
        "search_terms": result.get("search_terms", []),
        "filters": result.get("filters", {}),
        "explanation": result.get("explanation", "")
    }


# Code Intelligence Endpoints

@router.post("/intel/definition")
async def go_to_definition(request: CodeIntelRequest):
    """Find definition of symbol at position"""
    if not _code_intel:
        raise HTTPException(503, "Code intelligence not initialized")
    
    locations = _code_intel.go_to_definition(
        file_path=request.file_path,
        line=request.line,
        column=request.column,
        word=request.word or ""
    )
    
    return {
        "locations": [loc.to_dict() for loc in locations]
    }


@router.post("/intel/references")
async def find_references(word: str = Body(..., embed=True)):
    """Find all references to a symbol"""
    if not _code_intel:
        raise HTTPException(503, "Code intelligence not initialized")
    
    locations = _code_intel.find_references(word)
    
    return {
        "word": word,
        "references": [loc.to_dict() for loc in locations],
        "count": len(locations)
    }


@router.post("/intel/hover")
async def hover_info(request: CodeIntelRequest):
    """Get hover information at position"""
    if not _code_intel:
        raise HTTPException(503, "Code intelligence not initialized")
    
    info = _code_intel.get_hover(
        file_path=request.file_path,
        line=request.line,
        column=request.column
    )
    
    if not info:
        return {"contents": None}
    
    return {
        "contents": info.contents,
        "symbol": info.symbol.to_dict() if info.symbol else None
    }


@router.post("/intel/completions")
async def get_completions(request: CodeIntelRequest):
    """Get code completions"""
    if not _code_intel:
        raise HTTPException(503, "Code intelligence not initialized")
    
    completions = _code_intel.get_completions(
        file_path=request.file_path,
        line=request.line,
        column=request.column,
        prefix=request.word or ""
    )
    
    return {
        "completions": [
            {
                "label": c.label,
                "kind": c.kind.value,
                "detail": c.detail,
                "insertText": c.insert_text
            }
            for c in completions
        ]
    }


@router.get("/intel/symbols/{file_path:path}")
async def document_symbols(file_path: str):
    """Get all symbols in a document"""
    if not _code_intel:
        raise HTTPException(503, "Code intelligence not initialized")
    
    symbols = _code_intel.get_document_symbols(file_path)
    
    return {
        "file": file_path,
        "symbols": [s.to_dict() for s in symbols]
    }


# AI Assistant Endpoints

@router.post("/ai/chat")
async def ai_chat(request: AIQueryRequest):
    """Chat with AI assistant"""
    if not _ai_assistant:
        raise HTTPException(503, "AI assistant not initialized")
    
    from ..ai.assistant import CodeContext
    
    context = None
    if request.code_context:
        context = CodeContext(
            file_path="",
            language=request.language,
            content=request.code_context,
            selection=request.code_context
        )
    
    response = _ai_assistant.chat(
        session_id=request.session_id or "default",
        message=request.query,
        context=context
    )
    
    return {
        "response": response.content,
        "code_blocks": response.code_blocks
    }


@router.post("/ai/explain")
async def explain_code(code: str = Body(...), language: str = Body("python")):
    """Explain what code does"""
    if not _ai_assistant:
        raise HTTPException(503, "AI assistant not initialized")
    
    response = _ai_assistant.explain_code(code, language)
    
    return {
        "explanation": response.content,
        "code_blocks": response.code_blocks
    }


@router.post("/ai/generate")
async def generate_code(
    description: str = Body(...),
    language: str = Body("python"),
    context: str = Body("")
):
    """Generate code from description"""
    if not _ai_assistant:
        raise HTTPException(503, "AI assistant not initialized")
    
    response = _ai_assistant.generate_code(description, language, context)
    
    return {
        "response": response.content,
        "code_blocks": response.code_blocks
    }


@router.post("/ai/review")
async def review_code(code: str = Body(...), language: str = Body("python")):
    """Review code for issues"""
    if not _ai_assistant:
        raise HTTPException(503, "AI assistant not initialized")
    
    response = _ai_assistant.review_code(code, language)
    
    return {
        "review": response.content,
        "suggestions": response.suggestions
    }


# Analysis Endpoints

@router.post("/analysis/quality")
async def analyze_quality(request: AnalysisRequest):
    """Analyze code quality"""
    if not _quality_analyzer:
        # Use local instance
        from ..analysis.quality import CodeQualityAnalyzer
        analyzer = CodeQualityAnalyzer(request.language)
    else:
        analyzer = _quality_analyzer
    
    result = analyzer.analyze_file(request.file_path, request.content)
    
    return result


@router.post("/analysis/security")
async def scan_security(request: AnalysisRequest):
    """Scan for security vulnerabilities"""
    from ..analysis.quality import SecurityScanner
    
    scanner = SecurityScanner(request.language)
    issues = scanner.scan(request.file_path, request.content)
    
    return {
        "file": request.file_path,
        "issues": [i.to_dict() for i in issues],
        "count": len(issues)
    }


@router.post("/analysis/complexity")
async def analyze_complexity(request: AnalysisRequest):
    """Analyze code complexity"""
    from ..analysis.quality import ComplexityAnalyzer
    
    analyzer = ComplexityAnalyzer(request.language)
    metrics = analyzer.analyze(request.content)
    
    return {
        "file": request.file_path,
        "metrics": metrics.to_dict()
    }


# Cache Endpoints

@router.get("/cache/stats")
async def cache_stats():
    """Get cache statistics"""
    from ..cache import CacheManager
    
    manager = CacheManager()
    return manager.get_stats()


@router.post("/cache/clear")
async def clear_cache():
    """Clear all caches"""
    from ..cache import CacheManager
    
    manager = CacheManager()
    manager.clear_all()
    
    return {"status": "cleared"}
