"""
Code Notebooks

Sourcegraph-inspired interactive code notebooks for
exploration, documentation, and sharing code insights.
"""

from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import uuid
import structlog

logger = structlog.get_logger()


class CellType(Enum):
    """Types of notebook cells"""
    MARKDOWN = "markdown"
    CODE = "code"
    QUERY = "query"
    FILE = "file"
    SYMBOL = "symbol"
    COMPUTE = "compute"


class CellStatus(Enum):
    """Cell execution status"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class CellOutput:
    """Output from a cell execution"""
    output_type: str  # text, code, table, chart, error
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class NotebookCell:
    """A cell in a code notebook"""
    id: str
    cell_type: CellType
    content: str
    language: str = "python"
    outputs: List[CellOutput] = field(default_factory=list)
    status: CellStatus = CellStatus.IDLE
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.cell_type.value,
            "content": self.content,
            "language": self.language,
            "outputs": [
                {"type": o.output_type, "content": o.content}
                for o in self.outputs
            ],
            "status": self.status.value,
            "metadata": self.metadata
        }


@dataclass
class Notebook:
    """Interactive code notebook"""
    id: str
    title: str
    description: str = ""
    cells: List[NotebookCell] = field(default_factory=list)
    author: str = ""
    tags: List[str] = field(default_factory=list)
    is_public: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "cells": [c.to_dict() for c in self.cells],
            "author": self.author,
            "tags": self.tags,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class NotebookEngine:
    """
    Engine for creating and executing code notebooks.
    
    Features:
    - Markdown documentation cells
    - Code search query cells
    - File embedding cells
    - Symbol reference cells
    - Computed/dynamic content cells
    """
    
    def __init__(self, search_engine=None, code_intel=None):
        self.search_engine = search_engine
        self.code_intel = code_intel
        self.notebooks: Dict[str, Notebook] = {}
    
    def create_notebook(
        self,
        title: str,
        description: str = "",
        author: str = ""
    ) -> Notebook:
        """Create a new notebook"""
        notebook = Notebook(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            author=author
        )
        self.notebooks[notebook.id] = notebook
        logger.info("Created notebook", id=notebook.id, title=title)
        return notebook
    
    def add_cell(
        self,
        notebook_id: str,
        cell_type: CellType,
        content: str,
        language: str = "python",
        position: Optional[int] = None
    ) -> Optional[NotebookCell]:
        """Add a cell to a notebook"""
        notebook = self.notebooks.get(notebook_id)
        if not notebook:
            return None
        
        cell = NotebookCell(
            id=str(uuid.uuid4()),
            cell_type=cell_type,
            content=content,
            language=language
        )
        
        if position is not None:
            notebook.cells.insert(position, cell)
        else:
            notebook.cells.append(cell)
        
        notebook.updated_at = datetime.now()
        return cell
    
    def execute_cell(
        self,
        notebook_id: str,
        cell_id: str
    ) -> Optional[CellOutput]:
        """Execute a cell and return output"""
        notebook = self.notebooks.get(notebook_id)
        if not notebook:
            return None
        
        cell = next((c for c in notebook.cells if c.id == cell_id), None)
        if not cell:
            return None
        
        cell.status = CellStatus.RUNNING
        
        try:
            output = self._execute_cell_content(cell)
            cell.outputs.append(output)
            cell.status = CellStatus.SUCCESS
            return output
        except Exception as e:
            error_output = CellOutput(
                output_type="error",
                content=str(e)
            )
            cell.outputs.append(error_output)
            cell.status = CellStatus.ERROR
            return error_output
    
    def _execute_cell_content(self, cell: NotebookCell) -> CellOutput:
        """Execute cell based on type"""
        if cell.cell_type == CellType.MARKDOWN:
            return CellOutput(
                output_type="markdown",
                content=cell.content
            )
        
        elif cell.cell_type == CellType.QUERY:
            # Execute search query
            if self.search_engine:
                results = self.search_engine.search(cell.content, limit=10)
                return CellOutput(
                    output_type="search_results",
                    content=[r.to_dict() if hasattr(r, 'to_dict') else str(r) for r in results]
                )
            return CellOutput(output_type="text", content="Search engine not available")
        
        elif cell.cell_type == CellType.FILE:
            # Embed file content
            return CellOutput(
                output_type="code",
                content={
                    "path": cell.content,
                    "language": cell.language,
                    "content": f"# File: {cell.content}\n# Content would be loaded here"
                }
            )
        
        elif cell.cell_type == CellType.SYMBOL:
            # Show symbol definition
            if self.code_intel:
                symbols = self.code_intel.find_references(cell.content)
                return CellOutput(
                    output_type="symbols",
                    content=[s.to_dict() if hasattr(s, 'to_dict') else str(s) for s in symbols]
                )
            return CellOutput(output_type="text", content="Code intel not available")
        
        elif cell.cell_type == CellType.COMPUTE:
            # Execute Python code (sandboxed in real implementation)
            return CellOutput(
                output_type="text",
                content="Code execution not implemented for security"
            )
        
        else:
            return CellOutput(
                output_type="text",
                content=cell.content
            )
    
    def execute_all(self, notebook_id: str) -> List[CellOutput]:
        """Execute all cells in a notebook"""
        notebook = self.notebooks.get(notebook_id)
        if not notebook:
            return []
        
        outputs = []
        for cell in notebook.cells:
            output = self.execute_cell(notebook_id, cell.id)
            if output:
                outputs.append(output)
        
        return outputs
    
    def export_markdown(self, notebook_id: str) -> str:
        """Export notebook as Markdown"""
        notebook = self.notebooks.get(notebook_id)
        if not notebook:
            return ""
        
        md = f"# {notebook.title}\n\n"
        md += f"{notebook.description}\n\n"
        
        for cell in notebook.cells:
            if cell.cell_type == CellType.MARKDOWN:
                md += f"{cell.content}\n\n"
            elif cell.cell_type == CellType.CODE:
                md += f"```{cell.language}\n{cell.content}\n```\n\n"
            elif cell.cell_type == CellType.QUERY:
                md += f"**Search Query:** `{cell.content}`\n\n"
            elif cell.cell_type == CellType.FILE:
                md += f"**File:** `{cell.content}`\n\n"
            elif cell.cell_type == CellType.SYMBOL:
                md += f"**Symbol:** `{cell.content}`\n\n"
        
        return md
    
    def export_json(self, notebook_id: str) -> str:
        """Export notebook as JSON"""
        notebook = self.notebooks.get(notebook_id)
        if not notebook:
            return "{}"
        
        return json.dumps(notebook.to_dict(), indent=2, default=str)
    
    def import_json(self, json_str: str) -> Optional[Notebook]:
        """Import notebook from JSON"""
        try:
            data = json.loads(json_str)
            
            notebook = Notebook(
                id=data.get("id", str(uuid.uuid4())),
                title=data["title"],
                description=data.get("description", ""),
                author=data.get("author", ""),
                tags=data.get("tags", [])
            )
            
            for cell_data in data.get("cells", []):
                cell = NotebookCell(
                    id=cell_data.get("id", str(uuid.uuid4())),
                    cell_type=CellType(cell_data["type"]),
                    content=cell_data["content"],
                    language=cell_data.get("language", "python")
                )
                notebook.cells.append(cell)
            
            self.notebooks[notebook.id] = notebook
            return notebook
            
        except Exception as e:
            logger.error("Failed to import notebook", error=str(e))
            return None
    
    def get_notebook(self, notebook_id: str) -> Optional[Notebook]:
        """Get a notebook by ID"""
        return self.notebooks.get(notebook_id)
    
    def list_notebooks(
        self,
        author: Optional[str] = None,
        tag: Optional[str] = None
    ) -> List[Notebook]:
        """List notebooks with optional filters"""
        notebooks = list(self.notebooks.values())
        
        if author:
            notebooks = [n for n in notebooks if n.author == author]
        
        if tag:
            notebooks = [n for n in notebooks if tag in n.tags]
        
        return sorted(notebooks, key=lambda n: n.updated_at, reverse=True)
    
    def delete_notebook(self, notebook_id: str) -> bool:
        """Delete a notebook"""
        if notebook_id in self.notebooks:
            del self.notebooks[notebook_id]
            return True
        return False
