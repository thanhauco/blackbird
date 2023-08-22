"""
Tests for Ngram Tokenizer
"""

import pytest
from blackbird.core.ngram import NgramTokenizer, MultiNgramTokenizer


class TestNgramTokenizer:
    """Test suite for NgramTokenizer"""
    
    def test_basic_tokenization(self):
        """Test basic trigram tokenization"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize("limits")
        
        assert ngrams == ["lim", "imi", "mit", "its"]
    
    def test_short_string(self):
        """Test tokenization of string shorter than n"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize("ab")
        
        assert ngrams == ["ab"]
    
    def test_empty_string(self):
        """Test tokenization of empty string"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize("")
        
        assert ngrams == []
    
    def test_lowercase(self):
        """Test that tokenization lowercases by default"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize("ABC")
        
        assert ngrams == ["abc"]
    
    def test_no_lowercase(self):
        """Test tokenization without lowercasing"""
        tokenizer = NgramTokenizer(n=3, lowercase=False)
        ngrams = tokenizer.tokenize("ABC")
        
        assert ngrams == ["ABC"]
    
    def test_bigrams(self):
        """Test bigram tokenization"""
        tokenizer = NgramTokenizer(n=2)
        ngrams = tokenizer.tokenize("code")
        
        assert ngrams == ["co", "od", "de"]
    
    def test_unique_ngrams(self):
        """Test getting unique ngrams"""
        tokenizer = NgramTokenizer(n=3)
        unique = tokenizer.get_unique_ngrams("abcabc")
        
        assert unique == {"abc", "bca", "cab"}
    
    def test_query_tokenization(self):
        """Test query tokenization removes duplicates"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize_query("abcabc")
        
        # Should be unique, in order of first appearance
        assert len(ngrams) == len(set(ngrams))
    
    def test_code_tokenization(self):
        """Test code-aware tokenization"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize_code("onClick")
        
        # Should split camelCase
        assert "cli" in ngrams
        assert "cli" in ngrams  # from "Click" lowercased
    
    def test_with_positions(self):
        """Test tokenization with position tracking"""
        tokenizer = NgramTokenizer(n=3)
        positions = tokenizer.tokenize_with_positions("hello")
        
        assert len(positions) == 3
        assert positions[0].token == "hel"
        assert positions[0].start == 0
        assert positions[0].end == 3
    
    def test_with_boundaries(self):
        """Test tokenization with word boundaries"""
        tokenizer = NgramTokenizer(n=3)
        ngrams = tokenizer.tokenize_with_boundaries("foo")
        
        assert "^fo" in ngrams
        assert "foo" in ngrams
        assert "oo$" in ngrams
    
    def test_find_matches(self):
        """Test finding matching positions"""
        tokenizer = NgramTokenizer(n=3)
        matches = tokenizer.find_ngram_matches("hello world", "hello")
        
        assert len(matches) > 0
        # Matches should cover "hello"
        assert matches[0][0] == 0


class TestMultiNgramTokenizer:
    """Test suite for MultiNgramTokenizer"""
    
    def test_multi_tokenization(self):
        """Test multi-size ngram tokenization"""
        tokenizer = MultiNgramTokenizer(min_n=2, max_n=3)
        ngrams = tokenizer.tokenize("code")
        
        # Should have both bigrams and trigrams
        assert "co" in ngrams
        assert "cod" in ngrams
    
    def test_by_size(self):
        """Test getting ngrams grouped by size"""
        tokenizer = MultiNgramTokenizer(min_n=2, max_n=3)
        by_size = tokenizer.tokenize_by_size("code")
        
        assert 2 in by_size
        assert 3 in by_size
        assert by_size[2] == ["co", "od", "de"]
        assert by_size[3] == ["cod", "ode"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
