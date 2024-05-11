"""
Blackbird Search Module

Advanced search capabilities including structural search.
"""

from .structural import (
    StructuralSearchEngine,
    StructuralPattern,
    StructuralMatch,
    CombinatorialSearch,
    PatternType
)

__all__ = [
    "StructuralSearchEngine",
    "StructuralPattern",
    "StructuralMatch",
    "CombinatorialSearch",
    "PatternType"
]
