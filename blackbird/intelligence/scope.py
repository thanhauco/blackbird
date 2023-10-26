"""
Scope Analysis for Code Intelligence

Provides scope-aware analysis for better symbol resolution.
"""

from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class ScopeType(Enum):
    """Types of scopes"""
    GLOBAL = "global"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    BLOCK = "block"


@dataclass
class Scope:
    """Represents a scope in code"""
    name: str
    scope_type: ScopeType
    start_line: int
    end_line: int
    parent: Optional["Scope"] = None
    children: List["Scope"] = field(default_factory=list)
    symbols: Dict[str, "ScopedSymbol"] = field(default_factory=dict)


@dataclass
class ScopedSymbol:
    """Symbol with scope information"""
    name: str
    symbol_type: str
    scope: Scope
    line: int
    is_definition: bool = True


class ScopeAnalyzer:
    """Analyzes code scope for symbol resolution"""
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.root_scope: Optional[Scope] = None
        self.current_scope: Optional[Scope] = None
    
    def analyze(self, content: str, file_path: str = "") -> Scope:
        """Analyze scope structure of code"""
        lines = content.split("\n")
        
        self.root_scope = Scope(
            name=file_path or "module",
            scope_type=ScopeType.MODULE,
            start_line=1,
            end_line=len(lines)
        )
        self.current_scope = self.root_scope
        
        indent_stack = [(0, self.root_scope)]
        
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            
            # Calculate indentation
            indent = len(line) - len(line.lstrip())
            
            # Pop scopes that have ended
            while indent_stack and indent <= indent_stack[-1][0] and len(indent_stack) > 1:
                closed_scope = indent_stack.pop()[1]
                closed_scope.end_line = line_num - 1
            
            self.current_scope = indent_stack[-1][1]
            
            # Check for new scope
            new_scope = self._detect_scope(line, line_num)
            if new_scope:
                self.current_scope.children.append(new_scope)
                new_scope.parent = self.current_scope
                indent_stack.append((indent, new_scope))
                self.current_scope = new_scope
            
            # Extract symbols
            self._extract_symbols(line, line_num)
        
        return self.root_scope
    
    def _detect_scope(self, line: str, line_num: int) -> Optional[Scope]:
        """Detect if line starts a new scope"""
        stripped = line.strip()
        
        if self.language == "python":
            if stripped.startswith("class "):
                name = stripped.split()[1].split("(")[0].rstrip(":")
                return Scope(name, ScopeType.CLASS, line_num, line_num)
            elif stripped.startswith("def ") or stripped.startswith("async def "):
                parts = stripped.split()
                name_idx = 1 if parts[0] == "def" else 2
                name = parts[name_idx].split("(")[0]
                return Scope(name, ScopeType.FUNCTION, line_num, line_num)
        
        return None
    
    def _extract_symbols(self, line: str, line_num: int):
        """Extract symbols from line"""
        # Simple symbol extraction
        import re
        
        # Variable assignments
        match = re.match(r'\s*(\w+)\s*=', line)
        if match and self.current_scope:
            name = match.group(1)
            self.current_scope.symbols[name] = ScopedSymbol(
                name=name,
                symbol_type="variable",
                scope=self.current_scope,
                line=line_num
            )
    
    def find_symbol(self, name: str, at_line: int) -> Optional[ScopedSymbol]:
        """Find symbol visible at a given line"""
        scope = self._find_scope_at_line(at_line)
        
        while scope:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        
        return None
    
    def _find_scope_at_line(self, line: int) -> Optional[Scope]:
        """Find the innermost scope containing a line"""
        def search(scope: Scope) -> Optional[Scope]:
            if scope.start_line <= line <= scope.end_line:
                for child in scope.children:
                    found = search(child)
                    if found:
                        return found
                return scope
            return None
        
        if self.root_scope:
            return search(self.root_scope)
        return None
    
    def get_visible_symbols(self, at_line: int) -> List[ScopedSymbol]:
        """Get all symbols visible at a line"""
        symbols = []
        scope = self._find_scope_at_line(at_line)
        
        while scope:
            symbols.extend(scope.symbols.values())
            scope = scope.parent
        
        return symbols
