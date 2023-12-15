"""
Blackbird Analysis Module

Code analysis capabilities for quality and dependencies.
"""

from .quality import (
    CodeQualityAnalyzer,
    ComplexityAnalyzer,
    SecurityScanner,
    CodeDuplicateDetector,
    CodeIssue,
    ComplexityMetrics,
    QualityScore,
    Severity,
    IssueType
)

from .dependencies import (
    DependencyGraph,
    DependencyNode,
    ImportParser,
    Import,
    CrossRepoAnalyzer
)

__all__ = [
    "CodeQualityAnalyzer",
    "ComplexityAnalyzer",
    "SecurityScanner",
    "CodeDuplicateDetector",
    "CodeIssue",
    "ComplexityMetrics",
    "QualityScore",
    "Severity",
    "IssueType",
    "DependencyGraph",
    "DependencyNode",
    "ImportParser",
    "Import",
    "CrossRepoAnalyzer"
]
