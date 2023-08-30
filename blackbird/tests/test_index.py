"""
Tests for Inverted Index
"""

import pytest
from blackbird.core.index import InvertedIndex, PostingsList, Posting, SearchResult
from blackbird.core.document import CodeDocument


class TestPostingsList:
    """Test suite for PostingsList"""
    
    def test_add_posting(self):
        """Test adding a posting"""
        pl = PostingsList()
        pl.add(Posting(doc_id="doc1", score=1.0))
        
        assert len(pl) == 1
        assert "doc1" in pl.get_doc_ids()
    
    def test_remove_posting(self):
        """Test removing a posting"""
        pl = PostingsList()
        pl.add(Posting(doc_id="doc1", score=1.0))
        pl.add(Posting(doc_id="doc2", score=1.0))
        
        assert pl.remove("doc1")
        assert len(pl) == 1
        assert "doc1" not in pl.get_doc_ids()
    
    def test_merge_postings(self):
        """Test merging posting lists"""
        pl1 = PostingsList()
        pl1.add(Posting(doc_id="doc1", score=1.0))
        
        pl2 = PostingsList()
        pl2.add(Posting(doc_id="doc2", score=2.0))
        
        pl1.merge(pl2)
        
        assert len(pl1) == 2
        assert "doc1" in pl1.get_doc_ids()
        assert "doc2" in pl1.get_doc_ids()
    
    def test_sort_by_score(self):
        """Test that postings are sorted by score"""
        pl = PostingsList()
        pl.add(Posting(doc_id="doc1", score=1.0))
        pl.add(Posting(doc_id="doc2", score=3.0))
        pl.add(Posting(doc_id="doc3", score=2.0))
        
        postings = list(pl)
        
        # Should be sorted by score descending
        assert postings[0].doc_id == "doc2"
        assert postings[1].doc_id == "doc3"
        assert postings[2].doc_id == "doc1"


class TestInvertedIndex:
    """Test suite for InvertedIndex"""
    
    @pytest.fixture
    def sample_docs(self):
        """Create sample documents"""
        return [
            CodeDocument.create(
                repo_id="repo1",
                path="src/main.py",
                content="def onClick(): pass",
                language="python"
            ),
            CodeDocument.create(
                repo_id="repo1",
                path="src/utils.py",
                content="def helper(): return onClick()",
                language="python"
            ),
            CodeDocument.create(
                repo_id="repo2",
                path="app.js",
                content="function onClick() { alert('clicked'); }",
                language="javascript"
            )
        ]
    
    def test_add_document(self, sample_docs):
        """Test adding a document"""
        index = InvertedIndex()
        
        assert index.add_document(sample_docs[0])
        assert index.contains_document(sample_docs[0].id)
    
    def test_add_duplicate(self, sample_docs):
        """Test that duplicates are rejected"""
        index = InvertedIndex()
        
        assert index.add_document(sample_docs[0])
        assert not index.add_document(sample_docs[0])
    
    def test_remove_document(self, sample_docs):
        """Test removing a document"""
        index = InvertedIndex()
        index.add_document(sample_docs[0])
        
        assert index.remove_document(sample_docs[0].id)
        assert not index.contains_document(sample_docs[0].id)
    
    def test_basic_search(self, sample_docs):
        """Test basic search"""
        index = InvertedIndex()
        for doc in sample_docs:
            index.add_document(doc)
        
        # Search for "def" which appears in python docs
        results = index.search("def")
        
        assert len(results) >= 2  # At least 2 docs contain "def"
    
    def test_search_no_results(self, sample_docs):
        """Test search with no matches"""
        index = InvertedIndex()
        for doc in sample_docs:
            index.add_document(doc)
        
        results = index.search("nonexistent")
        
        assert len(results) == 0
    
    def test_search_limit(self, sample_docs):
        """Test search result limiting"""
        index = InvertedIndex()
        for doc in sample_docs:
            index.add_document(doc)
        
        # Search for something that matches multiple docs
        results = index.search("def", limit=1)
        
        assert len(results) == 1
    
    def test_search_ranking(self, sample_docs):
        """Test that results are ranked by score"""
        index = InvertedIndex()
        for doc in sample_docs:
            index.add_document(doc)
        
        results = index.search("onClick")
        
        # Verify descending score order
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score
    
    def test_get_stats(self, sample_docs):
        """Test getting index statistics"""
        index = InvertedIndex()
        for doc in sample_docs:
            index.add_document(doc)
        
        stats = index.get_stats()
        
        assert stats["document_count"] == 3
        assert stats["ngram_count"] > 0
        assert stats["total_postings"] > 0
    
    def test_merge_indices(self, sample_docs):
        """Test merging two indices"""
        index1 = InvertedIndex()
        index1.add_document(sample_docs[0])
        
        index2 = InvertedIndex()
        index2.add_document(sample_docs[1])
        
        index1.merge(index2)
        
        stats = index1.get_stats()
        assert stats["document_count"] == 2
    
    def test_empty_query(self):
        """Test search with empty query"""
        index = InvertedIndex()
        
        results = index.search("")
        
        assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
