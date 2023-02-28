"""
Ngram Tokenizer for Blackbird Search Engine

This module provides ngram tokenization for substring matching.
For example, with n=3 (trigrams), "limits" becomes ["lim", "imi", "mit", "its"]
"""

import re
from typing import List, Set, Iterator, Tuple
from dataclasses import dataclass
import unicodedata


@dataclass
class TokenPosition:
    """Represents a token with its position in the original text"""
    token: str
    start: int
    end: int


class NgramTokenizer:
    """
    Generates ngrams for indexing and search.
    
    Ngrams are overlapping substrings of length n that enable
    efficient substring matching through inverted index lookups.
    """
    
    def __init__(self, n: int = 3, lowercase: bool = True):
        """
        Initialize the tokenizer.
        
        Args:
            n: Size of ngrams (default 3 for trigrams)
            lowercase: Whether to lowercase text before tokenizing
        """
        if n < 1:
            raise ValueError("Ngram size must be at least 1")
        self.n = n
        self.lowercase = lowercase
        
        # Special tokens for word boundaries
        self.START_TOKEN = "^"
        self.END_TOKEN = "$"
    
    def _normalize(self, text: str) -> str:
        """
        Normalize text for consistent tokenization.
        
        - Converts to lowercase if enabled
        - Normalizes Unicode characters
        - Preserves important code characters
        """
        # Normalize Unicode
        text = unicodedata.normalize("NFKC", text)
        
        if self.lowercase:
            text = text.lower()
        
        return text
    
    def tokenize(self, text: str, include_positions: bool = False) -> List[str]:
        """
        Generate ngrams from text.
        
        Args:
            text: Input text to tokenize
            include_positions: If True, return TokenPosition objects
            
        Returns:
            List of ngram strings
            
        Example:
            >>> tokenizer = NgramTokenizer(n=3)
            >>> tokenizer.tokenize("limits")
            ['lim', 'imi', 'mit', 'its']
        """
        if not text:
            return []
        
        text = self._normalize(text)
        
        if len(text) < self.n:
            # For short strings, return the whole string as a token
            return [text] if text else []
        
        ngrams = []
        for i in range(len(text) - self.n + 1):
            ngram = text[i:i + self.n]
            ngrams.append(ngram)
        
        return ngrams
    
    def tokenize_with_positions(self, text: str) -> List[TokenPosition]:
        """
        Generate ngrams with their positions in the original text.
        
        Useful for highlighting matches in search results.
        """
        if not text:
            return []
        
        normalized = self._normalize(text)
        
        if len(normalized) < self.n:
            return [TokenPosition(normalized, 0, len(text))]
        
        positions = []
        for i in range(len(normalized) - self.n + 1):
            ngram = normalized[i:i + self.n]
            positions.append(TokenPosition(ngram, i, i + self.n))
        
        return positions
    
    def tokenize_with_boundaries(self, text: str) -> List[str]:
        """
        Generate ngrams with word boundary markers.
        
        Adds special start (^) and end ($) tokens to help
        match word beginnings and endings.
        
        Example:
            >>> tokenizer.tokenize_with_boundaries("foo")
            ['^fo', 'foo', 'oo$']
        """
        if not text:
            return []
        
        text = self._normalize(text)
        bounded = f"{self.START_TOKEN}{text}{self.END_TOKEN}"
        
        ngrams = []
        for i in range(len(bounded) - self.n + 1):
            ngram = bounded[i:i + self.n]
            ngrams.append(ngram)
        
        return ngrams
    
    def tokenize_code(self, code: str) -> List[str]:
        """
        Tokenize code with special handling for programming constructs.
        
        - Splits on camelCase and snake_case boundaries
        - Preserves operators and special characters
        - Generates ngrams for each token
        """
        if not code:
            return []
        
        # Split camelCase: insertBefore -> insert, Before
        code = re.sub(r'([a-z])([A-Z])', r'\1 \2', code)
        
        # Split snake_case: insert_before -> insert, before
        code = re.sub(r'_+', ' ', code)
        
        # Split on common separators while preserving them
        tokens = re.findall(r'[a-zA-Z0-9]+|[^\s\w]', code)
        
        all_ngrams = []
        for token in tokens:
            if len(token) >= self.n:
                all_ngrams.extend(self.tokenize(token))
            elif token.strip():
                # Keep short tokens as-is (operators, etc.)
                all_ngrams.append(self._normalize(token))
        
        return all_ngrams
    
    def tokenize_query(self, query: str) -> List[str]:
        """
        Tokenize a search query.
        
        Same as tokenize() but optimized for search queries.
        Returns unique ngrams in order of appearance.
        """
        ngrams = self.tokenize(query)
        
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for ng in ngrams:
            if ng not in seen:
                seen.add(ng)
                unique.append(ng)
        
        return unique
    
    def get_unique_ngrams(self, text: str) -> Set[str]:
        """
        Get unique ngrams as a set.
        
        Useful for document fingerprinting and similarity calculations.
        """
        return set(self.tokenize(text))
    
    def iter_ngrams(self, text: str) -> Iterator[str]:
        """
        Iterate over ngrams without creating a full list.
        
        Memory-efficient for large texts.
        """
        if not text:
            return
        
        text = self._normalize(text)
        
        if len(text) < self.n:
            yield text
            return
        
        for i in range(len(text) - self.n + 1):
            yield text[i:i + self.n]
    
    def estimate_ngram_count(self, text_length: int) -> int:
        """
        Estimate the number of ngrams for a text of given length.
        
        Useful for capacity planning.
        """
        if text_length < self.n:
            return 1 if text_length > 0 else 0
        return text_length - self.n + 1
    
    def find_ngram_matches(self, text: str, query: str) -> List[Tuple[int, int]]:
        """
        Find positions where query ngrams match in text.
        
        Returns list of (start, end) positions for highlighting.
        """
        if not text or not query:
            return []
        
        text_normalized = self._normalize(text)
        query_ngrams = set(self.tokenize(query))
        
        matches = []
        for i in range(len(text_normalized) - self.n + 1):
            ngram = text_normalized[i:i + self.n]
            if ngram in query_ngrams:
                matches.append((i, i + self.n))
        
        # Merge overlapping ranges
        if not matches:
            return []
        
        merged = [matches[0]]
        for start, end in matches[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        
        return merged


class MultiNgramTokenizer:
    """
    Tokenizer that generates ngrams of multiple sizes.
    
    Useful for matching both short and long substrings efficiently.
    """
    
    def __init__(self, min_n: int = 2, max_n: int = 4, lowercase: bool = True):
        """
        Initialize with a range of ngram sizes.
        
        Args:
            min_n: Minimum ngram size
            max_n: Maximum ngram size
            lowercase: Whether to lowercase text
        """
        if min_n < 1 or max_n < min_n:
            raise ValueError("Invalid ngram size range")
        
        self.min_n = min_n
        self.max_n = max_n
        self.tokenizers = {
            n: NgramTokenizer(n=n, lowercase=lowercase)
            for n in range(min_n, max_n + 1)
        }
    
    def tokenize(self, text: str) -> List[str]:
        """Generate ngrams of all configured sizes."""
        all_ngrams = []
        for tokenizer in self.tokenizers.values():
            all_ngrams.extend(tokenizer.tokenize(text))
        return all_ngrams
    
    def tokenize_by_size(self, text: str) -> dict:
        """Generate ngrams grouped by size."""
        return {
            n: tokenizer.tokenize(text)
            for n, tokenizer in self.tokenizers.items()
        }
