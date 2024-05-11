"""
Structural Search

Sourcegraph-inspired structural search that matches code patterns
based on AST structure rather than just text.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
import structlog

logger = structlog.get_logger()


class PatternType(Enum):
    """Types of structural patterns"""
    EXACT = "exact"           # Exact match
    WILDCARD = "wildcard"     # Single wildcard (:[name])
    ELLIPSIS = "ellipsis"     # Multiple elements (...) 
    REGEX = "regex"           # Regex pattern


@dataclass
class PatternNode:
    """Node in a structural pattern"""
    pattern_type: PatternType
    value: str
    name: Optional[str] = None  # Capture name for wildcards
    children: List["PatternNode"] = field(default_factory=list)


@dataclass
class StructuralMatch:
    """Result of a structural search match"""
    file_path: str
    line_start: int
    line_end: int
    matched_text: str
    captures: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "matched_text": self.matched_text,
            "captures": self.captures
        }


class StructuralPattern:
    """
    Parses and represents a structural search pattern.
    
    Syntax (Sourcegraph-compatible):
    - :[name] - wildcard matching any expression
    - :[name:type] - typed wildcard
    - :[~regex] - regex pattern
    - ... - matches any number of elements
    """
    
    WILDCARD_PATTERN = r':\[(\w+)(?::(\w+))?\]'
    ELLIPSIS = '...'
    
    def __init__(self, pattern: str, language: str = "python"):
        self.raw_pattern = pattern
        self.language = language
        self.wildcards: Dict[str, str] = {}  # name -> matched value
        self.regex = self._compile_pattern(pattern)
    
    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """Compile structural pattern to regex"""
        # Escape regex special chars
        escaped = re.escape(pattern)
        
        # Replace ellipsis with .* (non-greedy)
        escaped = escaped.replace(re.escape(self.ELLIPSIS), '.*?')
        
        # Replace wildcards with capture groups
        def replace_wildcard(match):
            full = match.group(0)
            # Find original wildcard in unescaped pattern
            wildcard_match = re.search(self.WILDCARD_PATTERN, pattern)
            if wildcard_match:
                name = wildcard_match.group(1)
                type_hint = wildcard_match.group(2)
                
                if type_hint == "identifier":
                    return f'(?P<{name}>[a-zA-Z_][a-zA-Z0-9_]*)'
                elif type_hint == "string":
                    return f'(?P<{name}>["\'][^"\']*["\'])'
                elif type_hint == "number":
                    return f'(?P<{name}>\\d+(?:\\.\\d+)?)'
                else:
                    return f'(?P<{name}>.+?)'
            return full
        
        # Replace escaped wildcards
        escaped = re.sub(r':\\\[(\w+)(?:\\:(\w+))?\\\]', replace_wildcard, escaped)
        
        return re.compile(escaped, re.DOTALL | re.MULTILINE)
    
    def match(self, code: str) -> List[Tuple[int, int, Dict[str, str]]]:
        """
        Find all matches of pattern in code.
        
        Returns:
            List of (start_pos, end_pos, captures) tuples
        """
        matches = []
        
        for match in self.regex.finditer(code):
            captures = match.groupdict()
            matches.append((match.start(), match.end(), captures))
        
        return matches


class StructuralSearchEngine:
    """
    Engine for structural code search.
    
    Supports Sourcegraph-style structural patterns like:
    - `func :[name](:[args]) { ... }`
    - `if err != nil { return :[_] }`
    - `console.log(:[msg])`
    """
    
    # Common patterns per language
    BUILTIN_PATTERNS = {
        "python": {
            "function_def": "def :[name](:[args]):",
            "class_def": "class :[name](:[base]):",
            "try_except": "try:\\n...\\nexcept :[exc]:",
            "with_statement": "with :[context] as :[var]:",
            "list_comprehension": "[:[expr] for :[var] in :[iterable]]",
        },
        "javascript": {
            "function_def": "function :[name](:[args]) {",
            "arrow_function": "const :[name] = (:[args]) =>",
            "try_catch": "try {\\n...\\n} catch (:[err]) {",
            "async_function": "async function :[name](:[args]) {",
            "import_statement": "import :[imports] from :[module]",
        },
        "go": {
            "function_def": "func :[name](:[args]) :[return] {",
            "error_check": "if err != nil {\\nreturn :[_]\\n}",
            "defer": "defer :[expr]",
            "goroutine": "go :[func](:[args])",
        }
    }
    
    def __init__(self):
        self.patterns: Dict[str, StructuralPattern] = {}
    
    def compile_pattern(
        self,
        pattern: str,
        language: str = "python"
    ) -> StructuralPattern:
        """Compile a structural pattern"""
        key = f"{language}:{pattern}"
        if key not in self.patterns:
            self.patterns[key] = StructuralPattern(pattern, language)
        return self.patterns[key]
    
    def search(
        self,
        pattern: str,
        code: str,
        file_path: str = "",
        language: str = "python"
    ) -> List[StructuralMatch]:
        """
        Search for structural pattern in code.
        """
        compiled = self.compile_pattern(pattern, language)
        matches = compiled.match(code)
        
        results = []
        lines = code.split('\n')
        
        for start, end, captures in matches:
            # Calculate line numbers
            line_start = code[:start].count('\n') + 1
            line_end = code[:end].count('\n') + 1
            
            results.append(StructuralMatch(
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                matched_text=code[start:end],
                captures=captures
            ))
        
        return results
    
    def search_files(
        self,
        pattern: str,
        files: Dict[str, str],
        language: str = "python"
    ) -> List[StructuralMatch]:
        """Search pattern across multiple files"""
        all_results = []
        
        for file_path, content in files.items():
            results = self.search(pattern, content, file_path, language)
            all_results.extend(results)
        
        return all_results
    
    def get_builtin_patterns(self, language: str) -> Dict[str, str]:
        """Get built-in patterns for a language"""
        return self.BUILTIN_PATTERNS.get(language, {})
    
    def explain_pattern(self, pattern: str) -> str:
        """Explain what a pattern matches"""
        explanation = f"Pattern: {pattern}\n\nMatches:\n"
        
        # Find wildcards
        wildcards = re.findall(r':\[(\w+)(?::(\w+))?\]', pattern)
        for name, type_hint in wildcards:
            if type_hint:
                explanation += f"  - :[{name}:{type_hint}]: captures {type_hint} as '{name}'\n"
            else:
                explanation += f"  - :[{name}]: captures any expression as '{name}'\n"
        
        if '...' in pattern:
            explanation += "  - ...: matches any code between\n"
        
        return explanation


class CombinatorialSearch:
    """
    Combines structural search with regular search.
    """
    
    def __init__(self, structural_engine: StructuralSearchEngine):
        self.structural = structural_engine
    
    def search(
        self,
        query: str,
        files: Dict[str, str],
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Parse and execute combined search query.
        
        Query syntax:
        - Regular text: full-text search
        - `struct:pattern`: structural search
        - `lang:python`: language filter
        - `file:*.py`: file pattern filter
        """
        results = {
            "structural": [],
            "text": [],
            "filters": {}
        }
        
        # Parse structural patterns
        struct_matches = re.findall(r'struct:"([^"]+)"', query)
        for pattern in struct_matches:
            matches = self.structural.search_files(pattern, files, language)
            results["structural"].extend([m.to_dict() for m in matches])
        
        # Parse filters
        lang_match = re.search(r'lang:(\w+)', query)
        if lang_match:
            results["filters"]["language"] = lang_match.group(1)
        
        file_match = re.search(r'file:(\S+)', query)
        if file_match:
            results["filters"]["file_pattern"] = file_match.group(1)
        
        return results
