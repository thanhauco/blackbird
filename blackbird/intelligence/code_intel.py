"""
Code Intelligence Module

Provides IDE-like features: go-to-definition, find-references,
hover information, and scope analysis using AST parsing.
"""

from typing import List, Dict, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re
import structlog

from .scope import ScopeAnalyzer, Scope, ScopedSymbol

logger = structlog.get_logger()

# Try to import tree-sitter
try:
    import tree_sitter
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not available, using regex fallback")


class SymbolKind(Enum):
    """Kind of code symbol"""
    FILE = "file"
    MODULE = "module"
    NAMESPACE = "namespace"
    PACKAGE = "package"
    CLASS = "class"
    METHOD = "method"
    PROPERTY = "property"
    FIELD = "field"
    CONSTRUCTOR = "constructor"
    ENUM = "enum"
    INTERFACE = "interface"
    FUNCTION = "function"
    VARIABLE = "variable"
    CONSTANT = "constant"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    KEY = "key"
    NULL = "null"
    ENUM_MEMBER = "enum_member"
    STRUCT = "struct"
    EVENT = "event"
    OPERATOR = "operator"
    TYPE_PARAMETER = "type_parameter"


@dataclass
class Location:
    """Source code location"""
    file_path: str
    line: int
    column: int
    end_line: int = 0
    end_column: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column
        }


@dataclass
class Symbol:
    """
    Code symbol with location and metadata.
    """
    name: str
    kind: SymbolKind
    location: Location
    container: Optional[str] = None  # Parent symbol name
    signature: Optional[str] = None
    documentation: Optional[str] = None
    references: List[Location] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "location": self.location.to_dict(),
            "container": self.container,
            "signature": self.signature,
            "documentation": self.documentation
        }


@dataclass
class HoverInfo:
    """Information shown on hover"""
    contents: str
    range: Optional[Location] = None
    symbol: Optional[Symbol] = None


@dataclass
class CompletionItem:
    """Code completion suggestion"""
    label: str
    kind: SymbolKind
    detail: Optional[str] = None
    documentation: Optional[str] = None
    insert_text: Optional[str] = None
    sort_text: Optional[str] = None


class SymbolIndex:
    """
    Index of symbols across the codebase.
    
    Enables fast lookup for go-to-definition and find-references.
    """
    
    def __init__(self):
        # Symbol name -> list of symbols
        self.symbols: Dict[str, List[Symbol]] = {}
        
        # File -> list of symbols in that file
        self.file_symbols: Dict[str, List[Symbol]] = {}
        
        # Reference tracking: symbol name -> locations where it's used
        self.references: Dict[str, List[Location]] = {}
        
        # Import tracking
        self.imports: Dict[str, Dict[str, str]] = {}  # file -> {alias: module}
    
    def add_symbol(self, symbol: Symbol):
        """Add a symbol to the index"""
        if symbol.name not in self.symbols:
            self.symbols[symbol.name] = []
        self.symbols[symbol.name].append(symbol)
        
        if symbol.location.file_path not in self.file_symbols:
            self.file_symbols[symbol.location.file_path] = []
        self.file_symbols[symbol.location.file_path].append(symbol)
    
    def add_reference(self, name: str, location: Location):
        """Add a reference to a symbol"""
        if name not in self.references:
            self.references[name] = []
        self.references[name].append(location)
    
    def find_definition(self, name: str, file_path: Optional[str] = None) -> List[Symbol]:
        """
        Find definition(s) of a symbol.
        """
        candidates = self.symbols.get(name, [])
        
        if file_path:
            # Prefer definitions in the same file
            same_file = [s for s in candidates if s.location.file_path == file_path]
            if same_file:
                return same_file
        
        return candidates
    
    def find_references(self, name: str) -> List[Location]:
        """
        Find all references to a symbol.
        """
        refs = self.references.get(name, [])
        
        # Also include the definition locations
        for symbol in self.symbols.get(name, []):
            refs.append(symbol.location)
        
        return refs
    
    def get_symbols_in_file(self, file_path: str) -> List[Symbol]:
        """Get all symbols in a file"""
        return self.file_symbols.get(file_path, [])
    
    def search_symbols(self, query: str, limit: int = 20) -> List[Symbol]:
        """Search for symbols by name prefix"""
        results = []
        query_lower = query.lower()
        
        for name, symbols in self.symbols.items():
            if query_lower in name.lower():
                results.extend(symbols)
                if len(results) >= limit:
                    break
        
        return results[:limit]


class CodeAnalyzer:
    """
    Analyzes code to extract symbols, references, and scope information.
    """
    
    # Language-specific patterns for symbol extraction
    PATTERNS = {
        "python": {
            "function": r"^\s*(?:async\s+)?def\s+(\w+)\s*\(",
            "class": r"^\s*class\s+(\w+)\s*[:\(]",
            "variable": r"^\s*(\w+)\s*=\s*",
            "import": r"^\s*(?:from\s+(\S+)\s+)?import\s+(.+)",
        },
        "javascript": {
            "function": r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))",
            "class": r"class\s+(\w+)",
            "variable": r"(?:const|let|var)\s+(\w+)\s*=",
            "import": r"import\s+(?:{[^}]+}|\*\s+as\s+\w+|\w+)\s+from\s+['\"]([^'\"]+)['\"]",
        },
        "typescript": {
            "function": r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))",
            "class": r"class\s+(\w+)",
            "interface": r"interface\s+(\w+)",
            "type": r"type\s+(\w+)\s*=",
            "variable": r"(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=",
            "import": r"import\s+(?:{[^}]+}|\*\s+as\s+\w+|\w+)\s+from\s+['\"]([^'\"]+)['\"]",
        },
        "java": {
            "class": r"(?:public|private|protected)?\s*(?:static\s+)?class\s+(\w+)",
            "interface": r"(?:public|private|protected)?\s*interface\s+(\w+)",
            "method": r"(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(",
            "variable": r"(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*[=;]",
        },
        "go": {
            "function": r"func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
            "struct": r"type\s+(\w+)\s+struct\s*{",
            "interface": r"type\s+(\w+)\s+interface\s*{",
            "variable": r"(?:var|const)\s+(\w+)\s*(?:=|[^=])",
        }
    }
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.index = SymbolIndex()
    
    def analyze_file(self, file_path: str, content: str) -> List[Symbol]:
        """
        Analyze a file and extract symbols.
        """
        symbols = []
        patterns = self.PATTERNS.get(self.language, self.PATTERNS["python"])
        
        lines = content.split("\n")
        
        for line_num, line in enumerate(lines, 1):
            # Check each pattern type
            for kind_name, pattern in patterns.items():
                if kind_name == "import":
                    continue  # Handle imports separately
                
                match = re.search(pattern, line)
                if match:
                    # Get the first captured group that's not None
                    name = next((g for g in match.groups() if g), None)
                    if name:
                        kind = self._get_symbol_kind(kind_name)
                        
                        symbol = Symbol(
                            name=name,
                            kind=kind,
                            location=Location(
                                file_path=file_path,
                                line=line_num,
                                column=match.start() + 1,
                                end_line=line_num,
                                end_column=match.end() + 1
                            ),
                            signature=line.strip()
                        )
                        
                        symbols.append(symbol)
                        self.index.add_symbol(symbol)
        
        # Extract references
        self._extract_references(file_path, content)
        
        return symbols
    
    def _get_symbol_kind(self, kind_name: str) -> SymbolKind:
        """Map pattern name to SymbolKind"""
        mapping = {
            "function": SymbolKind.FUNCTION,
            "class": SymbolKind.CLASS,
            "method": SymbolKind.METHOD,
            "variable": SymbolKind.VARIABLE,
            "interface": SymbolKind.INTERFACE,
            "struct": SymbolKind.STRUCT,
            "type": SymbolKind.TYPE_PARAMETER,
        }
        return mapping.get(kind_name, SymbolKind.VARIABLE)
    
    def _extract_references(self, file_path: str, content: str):
        """Extract symbol references from code"""
        # Find all identifiers
        identifier_pattern = r'\b([a-zA-Z_]\w*)\b'
        
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for match in re.finditer(identifier_pattern, line):
                name = match.group(1)
                
                # Skip keywords
                if self._is_keyword(name):
                    continue
                
                location = Location(
                    file_path=file_path,
                    line=line_num,
                    column=match.start() + 1,
                    end_column=match.end() + 1
                )
                
                self.index.add_reference(name, location)
    
    def _is_keyword(self, name: str) -> bool:
        """Check if name is a language keyword"""
        keywords = {
            "python": {"def", "class", "if", "else", "elif", "for", "while", "try", 
                      "except", "finally", "with", "as", "import", "from", "return",
                      "yield", "raise", "pass", "break", "continue", "and", "or", 
                      "not", "in", "is", "lambda", "True", "False", "None", "async", "await"},
            "javascript": {"function", "class", "if", "else", "for", "while", "do",
                          "switch", "case", "break", "continue", "return", "try",
                          "catch", "finally", "throw", "new", "delete", "typeof",
                          "instanceof", "void", "this", "super", "const", "let", "var",
                          "true", "false", "null", "undefined", "async", "await", "import", "export"},
        }
        
        lang_keywords = keywords.get(self.language, keywords["python"])
        return name in lang_keywords
    
    def get_hover_info(self, file_path: str, line: int, column: int) -> Optional[HoverInfo]:
        """Get hover information at a position"""
        symbols = self.index.get_symbols_in_file(file_path)
        
        for symbol in symbols:
            loc = symbol.location
            if (loc.line == line and 
                loc.column <= column <= loc.end_column):
                return HoverInfo(
                    contents=f"**{symbol.kind.value}** `{symbol.name}`\n\n{symbol.signature or ''}",
                    symbol=symbol
                )
        
        return None
    
    def get_completions(
        self, 
        file_path: str, 
        line: int, 
        column: int,
        prefix: str
    ) -> List[CompletionItem]:
        """Get code completion suggestions"""
        completions = []
        
        # Search symbols matching prefix
        symbols = self.index.search_symbols(prefix, limit=50)
        
        for symbol in symbols:
            completions.append(CompletionItem(
                label=symbol.name,
                kind=symbol.kind,
                detail=symbol.signature,
                documentation=symbol.documentation,
                insert_text=symbol.name
            ))
        
        # Sort by relevance
        completions.sort(key=lambda x: (
            not x.label.startswith(prefix),
            len(x.label)
        ))
        
        return completions[:20]


class CodeIntelligenceService:
    """
    High-level code intelligence service providing IDE features.
    """
    
    def __init__(self):
        self.analyzers: Dict[str, CodeAnalyzer] = {}
        self.scope_analyzers: Dict[str, ScopeAnalyzer] = {}
        self.global_index = SymbolIndex()
    
    def get_analyzer(self, language: str) -> CodeAnalyzer:
        """Get or create analyzer for a language"""
        if language not in self.analyzers:
            self.analyzers[language] = CodeAnalyzer(language)
        return self.analyzers[language]
    
    def index_file(self, file_path: str, content: str, language: str):
        """Index a file for code intelligence"""
        # Symbol analysis
        analyzer = self.get_analyzer(language)
        symbols = analyzer.analyze_file(file_path, content)
        
        # Scope analysis
        if language == "python":  # Currently only Python supported for scope
            if language not in self.scope_analyzers:
                self.scope_analyzers[language] = ScopeAnalyzer(language)
            
            scope_analyzer = self.scope_analyzers[language]
            scope_analyzer.analyze(content, file_path)
        
        # Add to global index
        for symbol in symbols:
            self.global_index.add_symbol(symbol)
        
        logger.debug("Indexed file", path=file_path, symbols=len(symbols))
    
    def go_to_definition(
        self, 
        file_path: str, 
        line: int, 
        column: int,
        word: str
    ) -> List[Location]:
        """Go to definition of symbol at position"""
        definitions = self.global_index.find_definition(word, file_path)
        return [d.location for d in definitions]
    
    def find_references(self, word: str) -> List[Location]:
        """Find all references to a symbol"""
        return self.global_index.find_references(word)
    
    def get_hover(
        self, 
        file_path: str, 
        line: int, 
        column: int
    ) -> Optional[HoverInfo]:
        """Get hover information"""
        # Determine language from file extension
        ext = Path(file_path).suffix.lstrip(".")
        lang_map = {"py": "python", "js": "javascript", "ts": "typescript"}
        language = lang_map.get(ext, "python")
        
        analyzer = self.get_analyzer(language)
        return analyzer.get_hover_info(file_path, line, column)
    
    def get_completions(
        self,
        file_path: str,
        line: int,
        column: int,
        prefix: str
    ) -> List[CompletionItem]:
        """Get code completions"""
        ext = Path(file_path).suffix.lstrip(".")
        lang_map = {"py": "python", "js": "javascript", "ts": "typescript"}
        language = lang_map.get(ext, "python")
        
        analyzer = self.get_analyzer(language)
        return analyzer.get_completions(file_path, line, column, prefix)
    
    def get_document_symbols(self, file_path: str) -> List[Symbol]:
        """Get all symbols in a document"""
        return self.global_index.get_symbols_in_file(file_path)
    
    def workspace_symbol_search(self, query: str) -> List[Symbol]:
        """Search symbols across the workspace"""
        return self.global_index.search_symbols(query)
    
    def get_scope_variables(self, file_path: str, line: int) -> List[ScopedSymbol]:
        """Get all variables visible in the current scope"""
        # Determine language
        ext = Path(file_path).suffix.lstrip(".")
        language = "python" if ext == "py" else None
        
        if language and language in self.scope_analyzers:
            return self.scope_analyzers[language].get_visible_symbols(line)
        return []
