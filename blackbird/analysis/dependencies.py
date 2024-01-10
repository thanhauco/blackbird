"""
Dependency Graph Analysis

Analyzes import relationships and builds dependency graphs
for cross-repository code intelligence.
"""

from typing import List, Dict, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
import re
import structlog

logger = structlog.get_logger()


@dataclass
class Import:
    """Represents an import statement"""
    module: str
    name: Optional[str] = None  # Specific name imported
    alias: Optional[str] = None
    is_relative: bool = False
    line: int = 0


@dataclass
class DependencyNode:
    """Node in the dependency graph"""
    file_path: str
    module_name: str
    imports: List[Import] = field(default_factory=list)
    imported_by: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)


class ImportParser:
    """
    Parses import statements from source code.
    """
    
    PATTERNS = {
        "python": {
            "import": r'^import\s+(\S+)(?:\s+as\s+(\w+))?',
            "from_import": r'^from\s+(\S+)\s+import\s+(.+)',
        },
        "javascript": {
            "import": r"import\s+(?:(\w+)|{([^}]+)}|\*\s+as\s+(\w+))\s+from\s+['\"]([^'\"]+)['\"]",
            "require": r"(?:const|let|var)\s+(?:(\w+)|{([^}]+)})\s*=\s*require\(['\"]([^'\"]+)['\"]\)",
        },
        "typescript": {
            "import": r"import\s+(?:type\s+)?(?:(\w+)|{([^}]+)}|\*\s+as\s+(\w+))\s+from\s+['\"]([^'\"]+)['\"]",
        }
    }
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.patterns = self.PATTERNS.get(language, self.PATTERNS["python"])
    
    def parse(self, content: str) -> List[Import]:
        """Parse imports from source code"""
        imports = []
        lines = content.split("\n")
        
        for line_num, line in enumerate(lines, 1):
            parsed = self._parse_line(line.strip(), line_num)
            imports.extend(parsed)
        
        return imports
    
    def _parse_line(self, line: str, line_num: int) -> List[Import]:
        """Parse a single line for imports"""
        imports = []
        
        if self.language == "python":
            imports.extend(self._parse_python_import(line, line_num))
        elif self.language in ("javascript", "typescript"):
            imports.extend(self._parse_js_import(line, line_num))
        
        return imports
    
    def _parse_python_import(self, line: str, line_num: int) -> List[Import]:
        """Parse Python import statements"""
        imports = []
        
        # import module [as alias]
        match = re.match(self.patterns["import"], line)
        if match:
            module = match.group(1)
            alias = match.group(2) if len(match.groups()) > 1 else None
            imports.append(Import(
                module=module,
                alias=alias,
                line=line_num,
                is_relative=module.startswith(".")
            ))
            return imports
        
        # from module import name [as alias]
        match = re.match(self.patterns["from_import"], line)
        if match:
            module = match.group(1)
            names_part = match.group(2)
            
            # Parse individual names
            for name_spec in names_part.split(","):
                name_spec = name_spec.strip()
                if " as " in name_spec:
                    name, alias = name_spec.split(" as ")
                    name = name.strip()
                    alias = alias.strip()
                else:
                    name = name_spec
                    alias = None
                
                imports.append(Import(
                    module=module,
                    name=name,
                    alias=alias,
                    line=line_num,
                    is_relative=module.startswith(".")
                ))
        
        return imports
    
    def _parse_js_import(self, line: str, line_num: int) -> List[Import]:
        """Parse JavaScript/TypeScript import statements"""
        imports = []
        
        # ES6 import
        match = re.match(self.patterns["import"], line)
        if match:
            groups = match.groups()
            # Find the module path (last non-None group is the module)
            module = groups[-1] if groups[-1] else ""
            default_import = groups[0]
            named_imports = groups[1]
            namespace_import = groups[2] if len(groups) > 2 else None
            
            if default_import:
                imports.append(Import(
                    module=module,
                    name="default",
                    alias=default_import,
                    line=line_num
                ))
            
            if named_imports:
                for name in named_imports.split(","):
                    name = name.strip()
                    if " as " in name:
                        orig, alias = name.split(" as ")
                        imports.append(Import(
                            module=module,
                            name=orig.strip(),
                            alias=alias.strip(),
                            line=line_num
                        ))
                    else:
                        imports.append(Import(
                            module=module,
                            name=name,
                            line=line_num
                        ))
        
        return imports


class DependencyGraph:
    """
    Builds and queries the dependency graph.
    """
    
    def __init__(self):
        self.nodes: Dict[str, DependencyNode] = {}
        self.edges: Dict[str, Set[str]] = defaultdict(set)  # from -> to
        self.reverse_edges: Dict[str, Set[str]] = defaultdict(set)  # to -> from
    
    def add_file(
        self, 
        file_path: str, 
        content: str, 
        language: str = "python"
    ):
        """Add a file to the dependency graph"""
        parser = ImportParser(language)
        imports = parser.parse(content)
        
        # Derive module name from path
        module_name = self._path_to_module(file_path)
        
        node = DependencyNode(
            file_path=file_path,
            module_name=module_name,
            imports=imports
        )
        
        self.nodes[file_path] = node
        
        # Build edges
        for imp in imports:
            resolved = self._resolve_import(file_path, imp)
            if resolved:
                self.edges[file_path].add(resolved)
                self.reverse_edges[resolved].add(file_path)
    
    def _path_to_module(self, file_path: str) -> str:
        """Convert file path to module name"""
        path = Path(file_path)
        
        # Remove extension
        name = path.stem
        
        # Convert path separators to dots
        parts = list(path.parts[:-1]) + [name]
        
        # Filter out common prefixes
        if parts and parts[0] in ("src", "lib", "app"):
            parts = parts[1:]
        
        return ".".join(parts)
    
    def _resolve_import(self, file_path: str, imp: Import) -> Optional[str]:
        """Resolve an import to a file path"""
        if imp.is_relative:
            # Resolve relative to current file
            current_dir = Path(file_path).parent
            
            # Count leading dots
            module = imp.module
            levels = 0
            while module.startswith("."):
                levels += 1
                module = module[1:]
            
            # Go up directories
            for _ in range(levels - 1):
                current_dir = current_dir.parent
            
            # Build path
            if module:
                parts = module.split(".")
                resolved = current_dir / "/".join(parts)
            else:
                resolved = current_dir
            
            # Check for file or package
            for suffix in [".py", ".js", ".ts", "/index.py", "/index.js", "/index.ts"]:
                candidate = str(resolved) + suffix
                if candidate in self.nodes:
                    return candidate
        
        # Search in nodes for matching module
        for node_path, node in self.nodes.items():
            if node.module_name == imp.module or node.module_name.endswith("." + imp.module):
                return node_path
        
        return None
    
    def get_dependencies(self, file_path: str) -> List[str]:
        """Get files that this file depends on"""
        return list(self.edges.get(file_path, set()))
    
    def get_dependents(self, file_path: str) -> List[str]:
        """Get files that depend on this file"""
        return list(self.reverse_edges.get(file_path, set()))
    
    def get_import_chain(self, file_path: str) -> List[List[str]]:
        """Get chain of imports from this file"""
        chains = []
        visited = set()
        
        def dfs(current: str, chain: List[str]):
            if current in visited:
                return
            visited.add(current)
            chain.append(current)
            
            deps = self.get_dependencies(current)
            if not deps:
                if len(chain) > 1:
                    chains.append(chain.copy())
            else:
                for dep in deps:
                    dfs(dep, chain)
            
            chain.pop()
            visited.remove(current)
        
        dfs(file_path, [])
        return chains
    
    def find_circular_dependencies(self) -> List[List[str]]:
        """Find circular dependencies in the graph"""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.edges.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
            
            path.pop()
            rec_stack.remove(node)
        
        for node in self.nodes:
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    def get_most_imported(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most imported files"""
        counts = [(path, len(deps)) for path, deps in self.reverse_edges.items()]
        counts.sort(key=lambda x: x[1], reverse=True)
        return counts[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics"""
        return {
            "total_files": len(self.nodes),
            "total_edges": sum(len(deps) for deps in self.edges.values()),
            "avg_dependencies": sum(len(deps) for deps in self.edges.values()) / max(len(self.nodes), 1),
            "circular_dependencies": len(self.find_circular_dependencies()),
            "most_imported": self.get_most_imported(5)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export graph as dictionary"""
        return {
            "nodes": [
                {
                    "id": path,
                    "module": node.module_name,
                    "imports": len(node.imports),
                    "imported_by": len(self.reverse_edges.get(path, set()))
                }
                for path, node in self.nodes.items()
            ],
            "edges": [
                {"from": src, "to": dst}
                for src, dsts in self.edges.items()
                for dst in dsts
            ]
        }


class CrossRepoAnalyzer:
    """
    Analyzes dependencies across repositories.
    """
    
    def __init__(self):
        self.graphs: Dict[str, DependencyGraph] = {}  # repo_id -> graph
    
    def add_repo(self, repo_id: str, files: Dict[str, str], language: str = "python"):
        """Add a repository to the analyzer"""
        graph = DependencyGraph()
        
        for file_path, content in files.items():
            graph.add_file(file_path, content, language)
        
        self.graphs[repo_id] = graph
        
        logger.info("Added repo to analyzer", repo=repo_id, files=len(files))
    
    def find_shared_dependencies(self) -> Dict[str, List[str]]:
        """Find modules used across multiple repos"""
        module_usage: Dict[str, Set[str]] = defaultdict(set)
        
        for repo_id, graph in self.graphs.items():
            for node in graph.nodes.values():
                for imp in node.imports:
                    if not imp.is_relative:
                        module_usage[imp.module].add(repo_id)
        
        # Filter to modules used by multiple repos
        shared = {
            module: sorted(repos)
            for module, repos in module_usage.items()
            if len(repos) > 1
        }
        
        return shared
    
    def find_similar_patterns(self) -> List[Dict[str, Any]]:
        """Find similar import patterns across repos"""
        patterns = []
        
        # Extract import patterns per file
        for repo_id, graph in self.graphs.items():
            for path, node in graph.nodes.items():
                pattern = frozenset(imp.module for imp in node.imports if not imp.is_relative)
                if len(pattern) >= 3:  # Minimum pattern size
                    patterns.append({
                        "repo": repo_id,
                        "file": path,
                        "pattern": pattern
                    })
        
        # Find matching patterns
        # (simplified - full implementation would use similarity clustering)
        return patterns
