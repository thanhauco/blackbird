"""
Tests for Code Analysis
"""

import pytest
from blackbird.analysis.quality import (
    ComplexityAnalyzer, SecurityScanner, CodeQualityAnalyzer, Severity
)
from blackbird.analysis.dependencies import ImportParser, DependencyGraph
from blackbird.analysis.metrics import HalsteadMetrics, calculate_maintainability_index


class TestComplexityAnalyzer:
    """Tests for complexity analysis"""
    
    def test_cyclomatic_complexity(self):
        """Test cyclomatic complexity calculation"""
        analyzer = ComplexityAnalyzer("python")
        
        code = '''
def test(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    else:
        return 0
'''
        
        metrics = analyzer.analyze(code)
        
        assert metrics.cyclomatic_complexity >= 3
        assert metrics.num_functions == 1
    
    def test_nesting_depth(self):
        """Test max nesting depth calculation"""
        analyzer = ComplexityAnalyzer("python")
        
        code = '''
def deep():
    if True:
        if True:
            if True:
                pass
'''
        
        metrics = analyzer.analyze(code)
        
        assert metrics.max_nesting_depth >= 3


class TestSecurityScanner:
    """Tests for security scanning"""
    
    def test_detect_eval(self):
        """Test detecting eval usage"""
        scanner = SecurityScanner("python")
        
        code = '''
result = eval(user_input)
'''
        
        issues = scanner.scan("test.py", code)
        
        assert len(issues) >= 1
        assert any(i.rule_id == "SEC001" for i in issues)
    
    def test_detect_hardcoded_secret(self):
        """Test detecting hardcoded secrets"""
        scanner = SecurityScanner("python")
        
        code = '''
api_key = "sk-1234567890"
'''
        
        issues = scanner.scan("test.py", code)
        
        assert len(issues) >= 1
        assert any(i.severity == Severity.CRITICAL for i in issues)


class TestImportParser:
    """Tests for import parsing"""
    
    def test_parse_python_imports(self):
        """Test Python import parsing"""
        parser = ImportParser("python")
        
        code = '''
import os
from pathlib import Path
from . import local
'''
        
        imports = parser.parse(code)
        
        assert len(imports) == 3
        assert any(i.module == "os" for i in imports)
        assert any(i.is_relative for i in imports)


class TestHalsteadMetrics:
    """Tests for Halstead metrics"""
    
    def test_calculate_metrics(self):
        """Test Halstead metric calculation"""
        halstead = HalsteadMetrics("python")
        
        code = '''
def add(a, b):
    return a + b
'''
        
        metrics = halstead.calculate(code)
        
        assert metrics["vocabulary"] > 0
        assert metrics["volume"] > 0


class TestMaintainabilityIndex:
    """Tests for maintainability index"""
    
    def test_high_maintainability(self):
        """Test high maintainability score"""
        mi = calculate_maintainability_index(
            halstead_volume=100,
            cyclomatic_complexity=2,
            lines_of_code=10
        )
        
        assert mi > 50
    
    def test_low_maintainability(self):
        """Test low maintainability for complex code"""
        mi = calculate_maintainability_index(
            halstead_volume=5000,
            cyclomatic_complexity=50,
            lines_of_code=500
        )
        
        assert mi < 50
