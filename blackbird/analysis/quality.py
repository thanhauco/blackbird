"""
Code Analysis Module

Static analysis for code quality, complexity, and patterns.
"""

from typing import List, Dict, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
import math
import structlog

logger = structlog.get_logger()


class Severity(Enum):
    """Issue severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IssueType(Enum):
    """Types of code issues"""
    STYLE = "style"
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    COMPLEXITY = "complexity"
    DUPLICATION = "duplication"


@dataclass
class CodeIssue:
    """A detected code issue"""
    issue_type: IssueType
    severity: Severity
    message: str
    file_path: str
    line: int
    column: int = 0
    end_line: int = 0
    rule_id: str = ""
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "file": self.file_path,
            "line": self.line,
            "column": self.column,
            "rule_id": self.rule_id,
            "suggestion": self.suggestion
        }


@dataclass
class ComplexityMetrics:
    """Code complexity metrics"""
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    lines_of_code: int = 0
    lines_of_comments: int = 0
    num_functions: int = 0
    num_classes: int = 0
    max_nesting_depth: int = 0
    avg_function_length: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "cognitive_complexity": self.cognitive_complexity,
            "loc": self.lines_of_code,
            "comments": self.lines_of_comments,
            "functions": self.num_functions,
            "classes": self.num_classes,
            "max_nesting": self.max_nesting_depth,
            "avg_function_length": self.avg_function_length
        }


@dataclass
class QualityScore:
    """Overall code quality score"""
    overall: float  # 0-100
    maintainability: float
    reliability: float
    security: float
    
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    
    def grade(self) -> str:
        """Get letter grade"""
        if self.overall >= 90:
            return "A"
        elif self.overall >= 80:
            return "B"
        elif self.overall >= 70:
            return "C"
        elif self.overall >= 60:
            return "D"
        else:
            return "F"


class ComplexityAnalyzer:
    """
    Analyzes code complexity using various metrics.
    """
    
    # Patterns that increase cyclomatic complexity
    BRANCH_PATTERNS = {
        "python": [
            r'\bif\b', r'\belif\b', r'\belse\b',
            r'\bfor\b', r'\bwhile\b',
            r'\band\b', r'\bor\b',
            r'\btry\b', r'\bexcept\b',
            r'\bwith\b',
        ],
        "javascript": [
            r'\bif\b', r'\belse\b',
            r'\bfor\b', r'\bwhile\b', r'\bdo\b',
            r'&&', r'\|\|', r'\?',
            r'\btry\b', r'\bcatch\b',
            r'\bswitch\b', r'\bcase\b',
        ]
    }
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.patterns = self.BRANCH_PATTERNS.get(language, self.BRANCH_PATTERNS["python"])
    
    def analyze(self, content: str) -> ComplexityMetrics:
        """
        Analyze code complexity.
        """
        lines = content.split("\n")
        
        metrics = ComplexityMetrics()
        metrics.lines_of_code = len([l for l in lines if l.strip() and not l.strip().startswith("#")])
        metrics.lines_of_comments = len([l for l in lines if l.strip().startswith("#")])
        
        # Cyclomatic complexity
        metrics.cyclomatic_complexity = self._calculate_cyclomatic(content)
        
        # Cognitive complexity
        metrics.cognitive_complexity = self._calculate_cognitive(content)
        
        # Count functions/classes
        metrics.num_functions = len(re.findall(r'\bdef\s+\w+', content))
        metrics.num_classes = len(re.findall(r'\bclass\s+\w+', content))
        
        # Nesting depth
        metrics.max_nesting_depth = self._calculate_nesting(lines)
        
        # Average function length
        if metrics.num_functions > 0:
            metrics.avg_function_length = metrics.lines_of_code / metrics.num_functions
        
        return metrics
    
    def _calculate_cyclomatic(self, content: str) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity
        
        for pattern in self.patterns:
            complexity += len(re.findall(pattern, content))
        
        return complexity
    
    def _calculate_cognitive(self, content: str) -> int:
        """
        Calculate cognitive complexity.
        
        More weight to nested structures.
        """
        lines = content.split("\n")
        complexity = 0
        nesting = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Check for nesting increase
            if re.match(r'(if|for|while|try|with|def|class)\b', stripped):
                complexity += 1 + nesting
                if stripped.endswith(":"):
                    nesting += 1
            
            # Check for nesting decrease (simple heuristic)
            if stripped.startswith(("return", "break", "continue", "raise")):
                if nesting > 0:
                    nesting -= 1
        
        return complexity
    
    def _calculate_nesting(self, lines: List[str]) -> int:
        """Calculate maximum nesting depth"""
        max_depth = 0
        current_depth = 0
        
        for line in lines:
            if not line.strip():
                continue
            
            # Count leading spaces (assume 4-space indent)
            spaces = len(line) - len(line.lstrip())
            depth = spaces // 4
            
            if depth > max_depth:
                max_depth = depth
        
        return max_depth


class SecurityScanner:
    """
    Scans code for common security vulnerabilities.
    """
    
    VULNERABILITY_PATTERNS = {
        "python": [
            {
                "pattern": r"eval\s*\(",
                "message": "Use of eval() can lead to code injection",
                "severity": Severity.CRITICAL,
                "rule_id": "SEC001"
            },
            {
                "pattern": r"exec\s*\(",
                "message": "Use of exec() can lead to code injection",
                "severity": Severity.CRITICAL,
                "rule_id": "SEC002"
            },
            {
                "pattern": r"pickle\.loads?\(",
                "message": "Unpickling untrusted data is dangerous",
                "severity": Severity.ERROR,
                "rule_id": "SEC003"
            },
            {
                "pattern": r"subprocess\.(?:call|run|Popen)\([^)]*shell\s*=\s*True",
                "message": "shell=True can lead to command injection",
                "severity": Severity.ERROR,
                "rule_id": "SEC004"
            },
            {
                "pattern": r"os\.system\(",
                "message": "os.system() is vulnerable to command injection",
                "severity": Severity.ERROR,
                "rule_id": "SEC005"
            },
            {
                "pattern": r"password\s*=\s*['\"][^'\"]+['\"]",
                "message": "Hardcoded password detected",
                "severity": Severity.CRITICAL,
                "rule_id": "SEC006"
            },
            {
                "pattern": r"(?:api_key|apikey|secret)\s*=\s*['\"][^'\"]+['\"]",
                "message": "Hardcoded secret detected",
                "severity": Severity.CRITICAL,
                "rule_id": "SEC007"
            },
            {
                "pattern": r"\.execute\([^)]*%s",
                "message": "Potential SQL injection via string formatting",
                "severity": Severity.ERROR,
                "rule_id": "SEC008"
            },
            {
                "pattern": r"verify\s*=\s*False",
                "message": "SSL verification disabled",
                "severity": Severity.WARNING,
                "rule_id": "SEC009"
            },
        ],
        "javascript": [
            {
                "pattern": r"eval\s*\(",
                "message": "Use of eval() can lead to code injection",
                "severity": Severity.CRITICAL,
                "rule_id": "SEC001"
            },
            {
                "pattern": r"innerHTML\s*=",
                "message": "innerHTML can lead to XSS vulnerabilities",
                "severity": Severity.WARNING,
                "rule_id": "SEC010"
            },
            {
                "pattern": r"document\.write\s*\(",
                "message": "document.write can lead to XSS",
                "severity": Severity.WARNING,
                "rule_id": "SEC011"
            },
            {
                "pattern": r"password\s*[=:]\s*['\"][^'\"]+['\"]",
                "message": "Hardcoded password detected",
                "severity": Severity.CRITICAL,
                "rule_id": "SEC006"
            },
        ]
    }
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.patterns = self.VULNERABILITY_PATTERNS.get(
            language, 
            self.VULNERABILITY_PATTERNS["python"]
        )
    
    def scan(self, file_path: str, content: str) -> List[CodeIssue]:
        """
        Scan code for security vulnerabilities.
        """
        issues = []
        lines = content.split("\n")
        
        for line_num, line in enumerate(lines, 1):
            for vuln in self.patterns:
                if re.search(vuln["pattern"], line, re.IGNORECASE):
                    issues.append(CodeIssue(
                        issue_type=IssueType.SECURITY,
                        severity=vuln["severity"],
                        message=vuln["message"],
                        file_path=file_path,
                        line=line_num,
                        rule_id=vuln["rule_id"]
                    ))
        
        return issues


class CodeDuplicateDetector:
    """
    Detects duplicate or similar code segments.
    """
    
    def __init__(self, min_lines: int = 5, similarity_threshold: float = 0.8):
        self.min_lines = min_lines
        self.similarity_threshold = similarity_threshold
    
    def find_duplicates(
        self, 
        files: Dict[str, str]
    ) -> List[Tuple[str, str, float]]:
        """
        Find duplicate code across files.
        
        Returns:
            List of (file1, file2, similarity) tuples
        """
        duplicates = []
        
        file_list = list(files.items())
        
        for i, (file1, content1) in enumerate(file_list):
            for file2, content2 in file_list[i+1:]:
                similarity = self._calculate_similarity(content1, content2)
                
                if similarity >= self.similarity_threshold:
                    duplicates.append((file1, file2, similarity))
        
        return duplicates
    
    def _calculate_similarity(self, content1: str, content2: str) -> float:
        """Calculate code similarity using n-grams"""
        # Extract non-empty, non-comment lines
        lines1 = self._normalize_lines(content1)
        lines2 = self._normalize_lines(content2)
        
        if not lines1 or not lines2:
            return 0.0
        
        # Create n-gram sets
        ngrams1 = self._get_ngrams(lines1, n=3)
        ngrams2 = self._get_ngrams(lines2, n=3)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        
        return intersection / union if union > 0 else 0.0
    
    def _normalize_lines(self, content: str) -> List[str]:
        """Normalize code lines for comparison"""
        lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                # Remove variable names, keep structure
                normalized = re.sub(r'\b\w+\b', 'VAR', stripped)
                lines.append(normalized)
        return lines
    
    def _get_ngrams(self, lines: List[str], n: int = 3) -> Set[Tuple[str, ...]]:
        """Get n-grams from lines"""
        ngrams = set()
        for i in range(len(lines) - n + 1):
            ngram = tuple(lines[i:i+n])
            ngrams.add(ngram)
        return ngrams


class CodeQualityAnalyzer:
    """
    Comprehensive code quality analysis.
    """
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.complexity_analyzer = ComplexityAnalyzer(language)
        self.security_scanner = SecurityScanner(language)
        self.duplicate_detector = CodeDuplicateDetector()
    
    def analyze_file(
        self, 
        file_path: str, 
        content: str
    ) -> Dict[str, Any]:
        """
        Perform comprehensive analysis on a file.
        """
        # Complexity metrics
        complexity = self.complexity_analyzer.analyze(content)
        
        # Security scan
        security_issues = self.security_scanner.scan(file_path, content)
        
        # Style issues (simplified)
        style_issues = self._check_style(file_path, content)
        
        # Calculate quality score
        all_issues = security_issues + style_issues
        score = self._calculate_score(complexity, all_issues)
        
        return {
            "file": file_path,
            "complexity": complexity.to_dict(),
            "issues": [i.to_dict() for i in all_issues],
            "score": {
                "overall": score.overall,
                "maintainability": score.maintainability,
                "reliability": score.reliability,
                "security": score.security,
                "grade": score.grade()
            }
        }
    
    def _check_style(self, file_path: str, content: str) -> List[CodeIssue]:
        """Check for style issues"""
        issues = []
        lines = content.split("\n")
        
        for line_num, line in enumerate(lines, 1):
            # Line too long
            if len(line) > 120:
                issues.append(CodeIssue(
                    issue_type=IssueType.STYLE,
                    severity=Severity.INFO,
                    message=f"Line exceeds 120 characters ({len(line)})",
                    file_path=file_path,
                    line=line_num,
                    rule_id="STYLE001"
                ))
            
            # Trailing whitespace
            if line.rstrip() != line.rstrip('\n'):
                issues.append(CodeIssue(
                    issue_type=IssueType.STYLE,
                    severity=Severity.INFO,
                    message="Trailing whitespace",
                    file_path=file_path,
                    line=line_num,
                    rule_id="STYLE002"
                ))
        
        return issues
    
    def _calculate_score(
        self, 
        complexity: ComplexityMetrics, 
        issues: List[CodeIssue]
    ) -> QualityScore:
        """Calculate overall quality score"""
        # Start with perfect score
        maintainability = 100.0
        reliability = 100.0
        security = 100.0
        
        # Deduct for complexity
        if complexity.cyclomatic_complexity > 10:
            maintainability -= min(30, (complexity.cyclomatic_complexity - 10) * 3)
        
        if complexity.max_nesting_depth > 4:
            maintainability -= min(20, (complexity.max_nesting_depth - 4) * 5)
        
        # Deduct for issues
        for issue in issues:
            if issue.issue_type == IssueType.SECURITY:
                if issue.severity == Severity.CRITICAL:
                    security -= 25
                elif issue.severity == Severity.ERROR:
                    security -= 15
                else:
                    security -= 5
            elif issue.issue_type == IssueType.BUG:
                reliability -= 10
            else:
                maintainability -= 2
        
        # Clamp scores
        maintainability = max(0, maintainability)
        reliability = max(0, reliability)
        security = max(0, security)
        
        overall = (maintainability + reliability + security) / 3
        
        return QualityScore(
            overall=overall,
            maintainability=maintainability,
            reliability=reliability,
            security=security,
            issues_by_severity={
                "critical": len([i for i in issues if i.severity == Severity.CRITICAL]),
                "error": len([i for i in issues if i.severity == Severity.ERROR]),
                "warning": len([i for i in issues if i.severity == Severity.WARNING]),
                "info": len([i for i in issues if i.severity == Severity.INFO])
            }
        )
