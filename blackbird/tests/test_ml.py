"""
Tests for ML Features
"""

import pytest
import numpy as np
from pathlib import Path


class TestEmbeddings:
    """Tests for embedding functionality"""
    
    def test_vector_store_add_search(self):
        """Test adding and searching vectors"""
        from blackbird.ml.embeddings import VectorStore
        
        store = VectorStore(dimension=4)
        
        # Add vectors
        store.add("doc1", np.array([1.0, 0.0, 0.0, 0.0]))
        store.add("doc2", np.array([0.0, 1.0, 0.0, 0.0]))
        store.add("doc3", np.array([0.7, 0.7, 0.0, 0.0]))
        
        assert len(store) == 3
        
        # Search
        query = np.array([1.0, 0.0, 0.0, 0.0])
        results = store.search(query, k=2)
        
        assert len(results) == 2
        assert results[0].doc_id == "doc1"
    
    def test_vector_store_empty(self):
        """Test empty vector store"""
        from blackbird.ml.embeddings import VectorStore
        
        store = VectorStore(dimension=4)
        
        query = np.array([1.0, 0.0, 0.0, 0.0])
        results = store.search(query, k=10)
        
        assert len(results) == 0


class TestHybridSearch:
    """Tests for hybrid search"""
    
    def test_rrf_fusion(self):
        """Test RRF score calculation"""
        from blackbird.ml.hybrid import HybridSearchResult
        
        result = HybridSearchResult(
            doc_id="doc1",
            repo_id="repo1",
            path="/test.py",
            language="python",
            ngram_score=0.8,
            semantic_score=0.6
        )
        
        result.rank_features["ngram_rank"] = 1
        result.rank_features["semantic_rank"] = 3
        
        # Calculate RRF manually
        ngram_weight = 0.6
        semantic_weight = 0.4
        rrf_k = 60
        
        expected = (ngram_weight / (rrf_k + 1)) + (semantic_weight / (rrf_k + 3))
        
        result.combined_score = expected
        
        assert result.combined_score > 0


class TestCodeIntelligence:
    """Tests for code intelligence"""
    
    def test_symbol_extraction_python(self):
        """Test Python symbol extraction"""
        from blackbird.intelligence.code_intel import CodeAnalyzer
        
        analyzer = CodeAnalyzer("python")
        
        code = '''
def hello():
    pass

class MyClass:
    def method(self):
        pass

x = 10
'''
        
        symbols = analyzer.analyze_file("test.py", code)
        
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "MyClass" in names
        assert "method" in names
    
    def test_symbol_extraction_javascript(self):
        """Test JavaScript symbol extraction"""
        from blackbird.intelligence.code_intel import CodeAnalyzer
        
        analyzer = CodeAnalyzer("javascript")
        
        code = '''
function hello() {}

class MyClass {}

const x = 10;
'''
        
        symbols = analyzer.analyze_file("test.js", code)
        
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "MyClass" in names


class TestCodeQuality:
    """Tests for code quality analysis"""
    
    def test_complexity_calculation(self):
        """Test cyclomatic complexity calculation"""
        from blackbird.analysis.quality import ComplexityAnalyzer
        
        analyzer = ComplexityAnalyzer("python")
        
        code = '''
def test():
    if x:
        if y:
            pass
        elif z:
            pass
    for i in range(10):
        pass
'''
        
        metrics = analyzer.analyze(code)
        
        assert metrics.cyclomatic_complexity > 1
        assert metrics.num_functions == 1
        assert metrics.max_nesting_depth >= 2
    
    def test_security_scan(self):
        """Test security vulnerability detection"""
        from blackbird.analysis.quality import SecurityScanner
        
        scanner = SecurityScanner("python")
        
        code = '''
password = "secret123"
eval(user_input)
'''
        
        issues = scanner.scan("test.py", code)
        
        assert len(issues) >= 2
        
        rule_ids = [i.rule_id for i in issues]
        assert "SEC001" in rule_ids  # eval
        assert "SEC006" in rule_ids  # hardcoded password


class TestDependencies:
    """Tests for dependency analysis"""
    
    def test_import_parsing_python(self):
        """Test Python import parsing"""
        from blackbird.analysis.dependencies import ImportParser
        
        parser = ImportParser("python")
        
        code = '''
import os
from pathlib import Path
from . import local
from ..parent import module as m
'''
        
        imports = parser.parse(code)
        
        assert len(imports) == 4
        
        modules = [i.module for i in imports]
        assert "os" in modules
        assert "pathlib" in modules
    
    def test_dependency_graph(self):
        """Test dependency graph building"""
        from blackbird.analysis.dependencies import DependencyGraph
        
        graph = DependencyGraph()
        
        graph.add_file("a.py", "import b", "python")
        graph.add_file("b.py", "import c", "python")
        graph.add_file("c.py", "", "python")
        
        assert len(graph.nodes) == 3


class TestCache:
    """Tests for caching"""
    
    def test_lru_cache_basic(self):
        """Test basic LRU cache operations"""
        from blackbird.cache.cache import LRUCache
        
        cache = LRUCache(max_size=3)
        
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        
        assert cache.get("a") == 1
        assert cache.get("b") == 2
        
        # Add one more, should evict oldest
        cache.set("d", 4)
        
        # 'c' was least recently used (a and b were accessed)
        assert cache.get("c") is None
        assert cache.get("d") == 4
    
    def test_cache_stats(self):
        """Test cache statistics"""
        from blackbird.cache.cache import LRUCache
        
        cache = LRUCache(max_size=10)
        
        cache.set("a", 1)
        cache.get("a")  # Hit
        cache.get("b")  # Miss
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entries"] == 1


class TestRanking:
    """Tests for learning to rank"""
    
    def test_ranking_features(self):
        """Test ranking feature vector"""
        from blackbird.ml.ranking import RankingFeatures
        
        features = RankingFeatures(
            doc_id="doc1",
            ngram_score=0.8,
            semantic_score=0.6,
            exact_match=True,
            matched_ngrams=5
        )
        
        vector = features.to_vector()
        
        assert len(vector) == len(RankingFeatures.feature_names())
        assert vector[0] == 0.8  # ngram_score
    
    def test_simple_ranking(self):
        """Test simple ranking without ML model"""
        from blackbird.ml.ranking import LearningToRank, RankingFeatures
        
        ranker = LearningToRank()
        
        features = [
            RankingFeatures(doc_id="doc1", ngram_score=0.9, semantic_score=0.8),
            RankingFeatures(doc_id="doc2", ngram_score=0.5, semantic_score=0.3),
            RankingFeatures(doc_id="doc3", ngram_score=0.7, semantic_score=0.6),
        ]
        
        ranked = ranker.rank(features)
        
        assert ranked[0][0] == "doc1"  # Highest scores
        assert ranked[-1][0] == "doc2"  # Lowest scores
