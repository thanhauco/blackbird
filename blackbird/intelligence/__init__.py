"""
Blackbird Code Intelligence Module

IDE-like features for code navigation and understanding.
"""

from .code_intel import (
    CodeIntelligenceService,
    CodeAnalyzer,
    SymbolIndex,
    Symbol,
    SymbolKind,
    Location,
    HoverInfo,
    CompletionItem
)

__all__ = [
    "CodeIntelligenceService",
    "CodeAnalyzer",
    "SymbolIndex",
    "Symbol",
    "SymbolKind",
    "Location",
    "HoverInfo",
    "CompletionItem"
]
