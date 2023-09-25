"""
Query Expansion and Understanding

Provides query processing for better search results.
"""

from typing import List, Dict, Set, Optional
from dataclasses import dataclass
import re


@dataclass
class ExpandedQuery:
    """Query with expanded terms"""
    original: str
    terms: List[str]
    synonyms: Dict[str, List[str]]
    filters: Dict[str, str]


class QueryExpander:
    """Expands queries with synonyms and related terms"""
    
    # Common programming synonyms
    SYNONYMS = {
        "function": ["func", "def", "method", "fn"],
        "class": ["struct", "type", "interface"],
        "variable": ["var", "let", "const", "val"],
        "string": ["str", "text", "char"],
        "integer": ["int", "number", "num"],
        "array": ["list", "slice", "vector"],
        "dictionary": ["dict", "map", "hash", "object"],
        "error": ["exception", "err", "panic"],
        "async": ["await", "promise", "future"],
        "test": ["spec", "unittest", "pytest"],
    }
    
    def __init__(self):
        self.synonyms = self.SYNONYMS.copy()
    
    def expand(self, query: str) -> ExpandedQuery:
        """Expand query with synonyms"""
        terms = self._tokenize(query)
        expanded_synonyms = {}
        
        for term in terms:
            lower_term = term.lower()
            if lower_term in self.synonyms:
                expanded_synonyms[term] = self.synonyms[lower_term]
        
        # Extract filters
        filters = self._extract_filters(query)
        
        return ExpandedQuery(
            original=query,
            terms=terms,
            synonyms=expanded_synonyms,
            filters=filters
        )
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize query into terms"""
        # Split on whitespace and punctuation
        terms = re.findall(r'\w+', text)
        return terms
    
    def _extract_filters(self, query: str) -> Dict[str, str]:
        """Extract filter expressions from query"""
        filters = {}
        
        # Language filter: lang:python
        lang_match = re.search(r'lang:(\w+)', query)
        if lang_match:
            filters['language'] = lang_match.group(1)
        
        # Repo filter: repo:name
        repo_match = re.search(r'repo:(\S+)', query)
        if repo_match:
            filters['repo'] = repo_match.group(1)
        
        # File filter: file:*.py
        file_match = re.search(r'file:(\S+)', query)
        if file_match:
            filters['file'] = file_match.group(1)
        
        return filters


class QueryUnderstanding:
    """Understands query intent and structure"""
    
    def __init__(self):
        self.expander = QueryExpander()
    
    def analyze(self, query: str) -> Dict:
        """Analyze query for intent and structure"""
        expanded = self.expander.expand(query)
        
        intent = self._detect_intent(query)
        code_patterns = self._extract_code_patterns(query)
        
        return {
            "original": query,
            "intent": intent,
            "terms": expanded.terms,
            "synonyms": expanded.synonyms,
            "filters": expanded.filters,
            "code_patterns": code_patterns
        }
    
    def _detect_intent(self, query: str) -> str:
        """Detect query intent"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["how to", "example", "usage"]):
            return "example"
        elif any(kw in query_lower for kw in ["error", "fix", "bug", "issue"]):
            return "debug"
        elif any(kw in query_lower for kw in ["define", "what is", "explain"]):
            return "definition"
        elif any(kw in query_lower for kw in ["import", "require", "from"]):
            return "import"
        else:
            return "search"
    
    def _extract_code_patterns(self, query: str) -> List[str]:
        """Extract code-like patterns from query"""
        patterns = []
        
        # Function calls: func()
        patterns.extend(re.findall(r'\w+\(\)', query))
        
        # Method chains: obj.method
        patterns.extend(re.findall(r'\w+\.\w+', query))
        
        # Camel case identifiers
        patterns.extend(re.findall(r'[a-z]+[A-Z]\w*', query))
        
        # Snake case identifiers
        patterns.extend(re.findall(r'\w+_\w+', query))
        
        return patterns
