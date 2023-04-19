"""
Symbol Extractor for Blackbird Search Engine

Extracts code symbols (functions, classes, variables) from source files.
Uses regex-based parsing for common languages and tree-sitter for advanced parsing.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import structlog

from ..core.document import Symbol, SymbolType

logger = structlog.get_logger()


class SymbolExtractor:
    """
    Extracts symbols from code files.
    
    Supports multiple programming languages through regex patterns
    and optional tree-sitter integration for more accurate parsing.
    """
    
    # Language-specific patterns for symbol extraction
    PATTERNS = {
        "python": {
            SymbolType.FUNCTION: [
                r'^(?:async\s+)?def\s+(\w+)\s*\([^)]*\)',
            ],
            SymbolType.CLASS: [
                r'^class\s+(\w+)\s*(?:\([^)]*\))?:',
            ],
            SymbolType.VARIABLE: [
                r'^(\w+)\s*(?::\s*\w+)?\s*=',
            ],
            SymbolType.IMPORT: [
                r'^(?:from\s+[\w.]+\s+)?import\s+([\w,\s]+)',
            ],
        },
        "javascript": {
            SymbolType.FUNCTION: [
                r'(?:async\s+)?function\s+(\w+)\s*\([^)]*\)',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function',
            ],
            SymbolType.CLASS: [
                r'class\s+(\w+)\s*(?:extends\s+\w+\s*)?{',
            ],
            SymbolType.VARIABLE: [
                r'(?:const|let|var)\s+(\w+)\s*=',
            ],
            SymbolType.IMPORT: [
                r'import\s+(?:{[^}]+}|\w+)\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            ],
        },
        "typescript": {
            SymbolType.FUNCTION: [
                r'(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)',
                r'(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            ],
            SymbolType.CLASS: [
                r'class\s+(\w+)\s*(?:<[^>]*>)?\s*(?:extends\s+\w+\s*)?(?:implements\s+[\w,\s]+\s*)?{',
            ],
            SymbolType.INTERFACE: [
                r'interface\s+(\w+)\s*(?:<[^>]*>)?\s*(?:extends\s+[\w,\s]+\s*)?{',
            ],
            SymbolType.TYPE: [
                r'type\s+(\w+)\s*(?:<[^>]*>)?\s*=',
            ],
            SymbolType.VARIABLE: [
                r'(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=',
            ],
        },
        "java": {
            SymbolType.FUNCTION: [
                r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:\w+(?:<[^>]*>)?)\s+(\w+)\s*\([^)]*\)',
            ],
            SymbolType.CLASS: [
                r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)',
            ],
            SymbolType.INTERFACE: [
                r'(?:public\s+)?interface\s+(\w+)',
            ],
            SymbolType.VARIABLE: [
                r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:\w+(?:<[^>]*>)?)\s+(\w+)\s*[;=]',
            ],
        },
        "go": {
            SymbolType.FUNCTION: [
                r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*\)',
            ],
            SymbolType.TYPE: [
                r'type\s+(\w+)\s+(?:struct|interface)',
            ],
            SymbolType.VARIABLE: [
                r'(?:var|const)\s+(\w+)\s*(?:\w+)?\s*=',
            ],
        },
        "rust": {
            SymbolType.FUNCTION: [
                r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)',
            ],
            SymbolType.CLASS: [  # Structs in Rust
                r'(?:pub\s+)?struct\s+(\w+)',
            ],
            SymbolType.INTERFACE: [  # Traits in Rust
                r'(?:pub\s+)?trait\s+(\w+)',
            ],
            SymbolType.ENUM: [
                r'(?:pub\s+)?enum\s+(\w+)',
            ],
            SymbolType.VARIABLE: [
                r'(?:let|const|static)\s+(?:mut\s+)?(\w+)\s*(?::\s*[^=]+)?\s*=',
            ],
        },
        "ruby": {
            SymbolType.FUNCTION: [
                r'def\s+(?:self\.)?(\w+[?!]?)',
            ],
            SymbolType.CLASS: [
                r'class\s+(\w+)',
            ],
            SymbolType.MODULE: [
                r'module\s+(\w+)',
            ],
        },
        "cpp": {
            SymbolType.FUNCTION: [
                r'(?:\w+(?:<[^>]*>)?(?:\s*[*&])?\s+)+(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?(?:final\s*)?[{;]',
            ],
            SymbolType.CLASS: [
                r'(?:class|struct)\s+(\w+)\s*(?::\s*(?:public|private|protected)\s+\w+\s*)?[{;]',
            ],
            SymbolType.VARIABLE: [
                r'(?:\w+(?:<[^>]*>)?(?:\s*[*&])?\s+)(\w+)\s*[;=]',
            ],
        },
        "csharp": {
            SymbolType.FUNCTION: [
                r'(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?(?:virtual\s+)?(?:override\s+)?(?:\w+(?:<[^>]*>)?)\s+(\w+)\s*\([^)]*\)',
            ],
            SymbolType.CLASS: [
                r'(?:public|private|protected|internal)?\s*(?:abstract\s+)?(?:sealed\s+)?(?:partial\s+)?class\s+(\w+)',
            ],
            SymbolType.INTERFACE: [
                r'(?:public|private|protected|internal)?\s*interface\s+(\w+)',
            ],
            SymbolType.PROPERTY: [
                r'(?:public|private|protected|internal)?\s*(?:static\s+)?(?:\w+(?:<[^>]*>)?)\s+(\w+)\s*{\s*(?:get|set)',
            ],
        },
    }
    
    # Alias languages to their patterns
    LANGUAGE_ALIASES = {
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "c": "cpp",
        "h": "cpp",
        "hpp": "cpp",
        "cs": "csharp",
        "rs": "rust",
        "rb": "ruby",
    }
    
    def __init__(self, use_tree_sitter: bool = False):
        """
        Initialize the symbol extractor.
        
        Args:
            use_tree_sitter: Use tree-sitter for more accurate parsing
        """
        self.use_tree_sitter = use_tree_sitter
        self._tree_sitter_parsers = {}
        
        if use_tree_sitter:
            self._init_tree_sitter()
    
    def _init_tree_sitter(self):
        """Initialize tree-sitter parsers for supported languages"""
        try:
            import tree_sitter
            # Tree-sitter initialization would go here
            # For now, fall back to regex
            logger.warning(
                "Tree-sitter integration not fully implemented, "
                "falling back to regex-based extraction"
            )
        except ImportError:
            logger.warning(
                "Tree-sitter not available, using regex-based extraction"
            )
    
    def extract(
        self,
        content: str,
        language: str
    ) -> List[Symbol]:
        """
        Extract symbols from code content.
        
        Args:
            content: Source code content
            language: Programming language
            
        Returns:
            List of extracted symbols
        """
        # Normalize language name
        language = language.lower()
        language = self.LANGUAGE_ALIASES.get(language, language)
        
        # Get patterns for language
        patterns = self.PATTERNS.get(language)
        if not patterns:
            return []
        
        symbols = []
        lines = content.split('\n')
        
        for symbol_type, type_patterns in patterns.items():
            for pattern in type_patterns:
                regex = re.compile(pattern, re.MULTILINE)
                
                for match in regex.finditer(content):
                    name = match.group(1)
                    
                    # Skip if name is too short or looks like a keyword
                    if len(name) < 2 or name in self._get_keywords(language):
                        continue
                    
                    # Find line number
                    line_start = content[:match.start()].count('\n') + 1
                    line_end = content[:match.end()].count('\n') + 1
                    
                    # Get signature (for functions)
                    signature = None
                    if symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                        signature = self._extract_signature(
                            content, match.start(), match.end()
                        )
                    
                    # Get documentation (if available)
                    documentation = self._extract_docstring(
                        lines, line_start - 1, language
                    )
                    
                    symbols.append(Symbol(
                        name=name,
                        symbol_type=symbol_type,
                        line_start=line_start,
                        line_end=line_end,
                        signature=signature,
                        documentation=documentation
                    ))
        
        return self._deduplicate_symbols(symbols)
    
    def _extract_signature(
        self,
        content: str,
        start: int,
        end: int
    ) -> str:
        """Extract function signature"""
        # Find end of signature (opening brace or colon)
        sig_end = content.find('{', end)
        if sig_end == -1:
            sig_end = content.find(':', end)
        if sig_end == -1:
            sig_end = end + 100  # Limit signature length
        
        signature = content[start:min(sig_end, start + 200)].strip()
        signature = ' '.join(signature.split())  # Normalize whitespace
        
        return signature
    
    def _extract_docstring(
        self,
        lines: List[str],
        line_index: int,
        language: str
    ) -> Optional[str]:
        """Extract docstring/comment above a symbol"""
        if line_index <= 0:
            return None
        
        doc_lines = []
        
        # Check lines above for comments/docstrings
        i = line_index - 1
        while i >= 0 and i >= line_index - 10:  # Max 10 lines of doc
            line = lines[i].strip()
            
            if language == "python":
                if line.startswith('"""') or line.startswith("'''"):
                    # Multi-line docstring
                    doc_lines.insert(0, line.strip('"\''))
                    break
                elif line.startswith('#'):
                    doc_lines.insert(0, line[1:].strip())
                elif not line:
                    break
                else:
                    break
            elif language in ("javascript", "typescript", "java", "cpp", "csharp", "go", "rust"):
                if line.startswith('//'):
                    doc_lines.insert(0, line[2:].strip())
                elif line.startswith('*'):
                    doc_lines.insert(0, line[1:].strip())
                elif line.startswith('/*') or line.startswith('/**'):
                    break
                elif not line:
                    break
                else:
                    break
            elif language == "ruby":
                if line.startswith('#'):
                    doc_lines.insert(0, line[1:].strip())
                elif not line:
                    break
                else:
                    break
            else:
                break
            
            i -= 1
        
        return '\n'.join(doc_lines) if doc_lines else None
    
    def _get_keywords(self, language: str) -> set:
        """Get keywords for a language"""
        keywords = {
            "python": {
                "if", "else", "elif", "for", "while", "try", "except",
                "finally", "with", "return", "yield", "import", "from",
                "class", "def", "async", "await", "pass", "break",
                "continue", "raise", "and", "or", "not", "in", "is",
                "None", "True", "False", "lambda", "global", "nonlocal",
            },
            "javascript": {
                "if", "else", "for", "while", "do", "switch", "case",
                "break", "continue", "return", "function", "class",
                "const", "let", "var", "new", "this", "super", "typeof",
                "instanceof", "null", "undefined", "true", "false",
                "try", "catch", "finally", "throw", "async", "await",
            },
            "java": {
                "if", "else", "for", "while", "do", "switch", "case",
                "break", "continue", "return", "class", "interface",
                "public", "private", "protected", "static", "final",
                "abstract", "new", "this", "super", "null", "true", "false",
                "try", "catch", "finally", "throw", "throws", "void",
            },
        }
        return keywords.get(language, set())
    
    def _deduplicate_symbols(self, symbols: List[Symbol]) -> List[Symbol]:
        """Remove duplicate symbols (same name and type on same line)"""
        seen = set()
        unique = []
        
        for sym in symbols:
            key = (sym.name, sym.symbol_type, sym.line_start)
            if key not in seen:
                seen.add(key)
                unique.append(sym)
        
        return unique
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages"""
        return list(self.PATTERNS.keys())


def extract_symbols(content: str, language: str) -> List[Symbol]:
    """
    Convenience function to extract symbols.
    """
    extractor = SymbolExtractor()
    return extractor.extract(content, language)
