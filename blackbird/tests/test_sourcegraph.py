"""
Tests for Sourcegraph-inspired Features
"""

import pytest
from blackbird.search.structural import StructuralSearchEngine, StructuralPattern
from blackbird.monitors.code_monitor import CodeMonitor, MonitorRule, AlertSeverity
from blackbird.notebooks.notebook import NotebookEngine, CellType


class TestStructuralSearch:
    """Tests for structural search"""
    
    def test_simple_pattern(self):
        """Test simple pattern matching"""
        engine = StructuralSearchEngine()
        
        code = '''
def hello():
    pass

def world():
    pass
'''
        
        results = engine.search("def :[name]():", code, "test.py", "python")
        
        assert len(results) == 2
    
    def test_pattern_with_captures(self):
        """Test pattern with captured groups"""
        pattern = StructuralPattern("def :[name](:[args]):", "python")
        
        code = "def greet(name, age):"
        matches = pattern.match(code)
        
        assert len(matches) >= 1
    
    def test_builtin_patterns(self):
        """Test built-in patterns exist"""
        engine = StructuralSearchEngine()
        
        patterns = engine.get_builtin_patterns("python")
        
        assert "function_def" in patterns
        assert "class_def" in patterns


class TestCodeMonitor:
    """Tests for code monitors"""
    
    def test_default_rules(self):
        """Test default security rules are added"""
        monitor = CodeMonitor()
        
        assert len(monitor.rules) > 0
        assert "sec-001" in monitor.rules
    
    def test_scan_hardcoded_secret(self):
        """Test detecting hardcoded secrets"""
        monitor = CodeMonitor()
        
        code = '''
api_key = "sk-secret-key-12345"
'''
        
        alerts = monitor.scan("test.py", code)
        
        assert len(alerts) >= 1
        assert any(a.severity == AlertSeverity.CRITICAL for a in alerts)
    
    def test_scan_eval(self):
        """Test detecting eval usage"""
        monitor = CodeMonitor()
        
        code = '''
result = eval(user_input)
'''
        
        alerts = monitor.scan("test.py", code)
        
        assert len(alerts) >= 1
    
    def test_add_custom_rule(self):
        """Test adding custom monitoring rule"""
        monitor = CodeMonitor()
        
        rule = MonitorRule(
            id="custom-001",
            name="Custom Rule",
            description="Test custom rule",
            pattern=r"print\(",
            severity=AlertSeverity.INFO
        )
        
        monitor.add_rule(rule)
        
        assert "custom-001" in monitor.rules
    
    def test_acknowledge_alert(self):
        """Test acknowledging alerts"""
        monitor = CodeMonitor()
        
        code = 'password = "secret"'
        alerts = monitor.scan("test.py", code)
        
        if alerts:
            alert_id = alerts[0].id
            result = monitor.acknowledge_alert(alert_id)
            assert result is True
            assert alerts[0].acknowledged is True


class TestNotebooks:
    """Tests for code notebooks"""
    
    def test_create_notebook(self):
        """Test creating a notebook"""
        engine = NotebookEngine()
        
        notebook = engine.create_notebook(
            title="Test Notebook",
            description="A test notebook"
        )
        
        assert notebook is not None
        assert notebook.title == "Test Notebook"
    
    def test_add_cell(self):
        """Test adding cells to notebook"""
        engine = NotebookEngine()
        
        notebook = engine.create_notebook("Test")
        
        cell = engine.add_cell(
            notebook.id,
            CellType.MARKDOWN,
            "# Hello World"
        )
        
        assert cell is not None
        assert len(notebook.cells) == 1
    
    def test_export_markdown(self):
        """Test exporting notebook as Markdown"""
        engine = NotebookEngine()
        
        notebook = engine.create_notebook("Export Test")
        engine.add_cell(notebook.id, CellType.MARKDOWN, "# Header")
        engine.add_cell(notebook.id, CellType.CODE, "print('hello')", "python")
        
        md = engine.export_markdown(notebook.id)
        
        assert "# Export Test" in md
        assert "# Header" in md
        assert "```python" in md
    
    def test_export_import_json(self):
        """Test JSON export and import"""
        engine = NotebookEngine()
        
        notebook = engine.create_notebook("JSON Test")
        engine.add_cell(notebook.id, CellType.MARKDOWN, "Test content")
        
        json_str = engine.export_json(notebook.id)
        
        # Create new engine and import
        engine2 = NotebookEngine()
        imported = engine2.import_json(json_str)
        
        assert imported is not None
        assert imported.title == "JSON Test"
        assert len(imported.cells) == 1
