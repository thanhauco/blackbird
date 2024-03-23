"""
Tests for Code Intelligence
"""

import pytest
from blackbird.intelligence.code_intel import CodeAnalyzer, SymbolIndex, SymbolKind
from blackbird.intelligence.scope import ScopeAnalyzer, ScopeType


class TestScopeAnalyzer:
    """Tests for scope analysis"""
    
    def test_basic_scope_detection(self):
        """Test basic scope detection"""
        analyzer = ScopeAnalyzer("python")
        
        code = '''
def outer():
    x = 1
    def inner():
        y = 2
    return x
'''
        
        scope = analyzer.analyze(code, "test.py")
        
        assert scope.scope_type == ScopeType.MODULE
        assert len(scope.children) == 1
        assert scope.children[0].name == "outer"
    
    def test_class_scope(self):
        """Test class scope detection"""
        analyzer = ScopeAnalyzer("python")
        
        code = '''
class MyClass:
    def method(self):
        pass
'''
        
        scope = analyzer.analyze(code, "test.py")
        
        assert len(scope.children) == 1
        assert scope.children[0].scope_type == ScopeType.CLASS
        assert scope.children[0].name == "MyClass"
    
    def test_find_symbol(self):
        """Test finding symbols in scope"""
        analyzer = ScopeAnalyzer("python")
        
        code = '''
x = 1
def func():
    y = 2
'''
        
        analyzer.analyze(code, "test.py")
        
        # x should be visible at line 5
        symbol = analyzer.find_symbol("x", 5)
        assert symbol is not None
        assert symbol.name == "x"


class TestSymbolIndex:
    """Tests for symbol indexing"""
    
    def test_add_and_find(self):
        """Test adding and finding symbols"""
        from blackbird.intelligence.code_intel import Symbol, Location
        
        index = SymbolIndex()
        
        symbol = Symbol(
            name="test_func",
            kind=SymbolKind.FUNCTION,
            location=Location("test.py", 10, 1)
        )
        
        index.add_symbol(symbol)
        
        results = index.find_definition("test_func")
        assert len(results) == 1
        assert results[0].name == "test_func"
    
    def test_search_symbols(self):
        """Test symbol search by prefix"""
        from blackbird.intelligence.code_intel import Symbol, Location
        
        index = SymbolIndex()
        
        for name in ["get_user", "get_data", "set_user"]:
            index.add_symbol(Symbol(
                name=name,
                kind=SymbolKind.FUNCTION,
                location=Location("test.py", 1, 1)
            ))
        
        results = index.search_symbols("get")
        assert len(results) == 2
