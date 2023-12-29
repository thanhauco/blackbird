"""
Code Metrics Module

Provides additional code quality metrics.
"""

from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
import re
import math


@dataclass
class MaintainabilityIndex:
    """Halstead-based maintainability index"""
    halstead_volume: float
    cyclomatic_complexity: int
    lines_of_code: int
    maintainability_index: float
    
    def grade(self) -> str:
        """Get maintainability grade"""
        if self.maintainability_index >= 85:
            return "A"
        elif self.maintainability_index >= 65:
            return "B"
        elif self.maintainability_index >= 50:
            return "C"
        else:
            return "D"


class HalsteadMetrics:
    """Halstead complexity metrics"""
    
    def __init__(self, language: str = "python"):
        self.language = language
        self.operators = self._get_operators()
        self.keywords = self._get_keywords()
    
    def _get_operators(self) -> Set[str]:
        """Get operators for language"""
        return {
            "+", "-", "*", "/", "%", "**", "//",
            "==", "!=", "<", ">", "<=", ">=",
            "=", "+=", "-=", "*=", "/=",
            "and", "or", "not",
            "in", "is", "not in", "is not",
            ".", "(", ")", "[", "]", "{", "}", ",", ":", ";",
        }
    
    def _get_keywords(self) -> Set[str]:
        """Get keywords for language"""
        return {
            "def", "class", "if", "elif", "else",
            "for", "while", "try", "except", "finally",
            "with", "as", "import", "from", "return",
            "yield", "raise", "pass", "break", "continue",
            "lambda", "async", "await",
        }
    
    def calculate(self, code: str) -> Dict[str, float]:
        """Calculate Halstead metrics"""
        operators, operands = self._extract_tokens(code)
        
        n1 = len(set(operators))  # Distinct operators
        n2 = len(set(operands))   # Distinct operands
        N1 = len(operators)       # Total operators
        N2 = len(operands)        # Total operands
        
        # Avoid division by zero
        if n1 == 0 or n2 == 0 or N1 == 0 or N2 == 0:
            return {
                "vocabulary": 0,
                "length": 0,
                "volume": 0,
                "difficulty": 0,
                "effort": 0,
            }
        
        vocabulary = n1 + n2
        length = N1 + N2
        volume = length * math.log2(vocabulary) if vocabulary > 0 else 0
        difficulty = (n1 / 2) * (N2 / n2)
        effort = difficulty * volume
        
        return {
            "vocabulary": vocabulary,
            "length": length,
            "volume": volume,
            "difficulty": difficulty,
            "effort": effort,
        }
    
    def _extract_tokens(self, code: str) -> Tuple[List[str], List[str]]:
        """Extract operators and operands from code"""
        operators = []
        operands = []
        
        # Simple tokenization
        tokens = re.findall(r'[a-zA-Z_]\w*|[+\-*/%=<>!&|^~]+|[.,;:()[\]{}]', code)
        
        for token in tokens:
            if token in self.operators or token in self.keywords:
                operators.append(token)
            else:
                operands.append(token)
        
        return operators, operands


class CodeChurn:
    """Tracks code churn metrics"""
    
    def __init__(self):
        self.file_changes: Dict[str, List[Dict]] = {}
    
    def record_change(
        self,
        file_path: str,
        lines_added: int,
        lines_deleted: int,
        timestamp: float
    ):
        """Record a file change"""
        if file_path not in self.file_changes:
            self.file_changes[file_path] = []
        
        self.file_changes[file_path].append({
            "added": lines_added,
            "deleted": lines_deleted,
            "timestamp": timestamp
        })
    
    def get_churn_rate(self, file_path: str) -> float:
        """Get churn rate for a file"""
        if file_path not in self.file_changes:
            return 0.0
        
        changes = self.file_changes[file_path]
        total_changes = sum(c["added"] + c["deleted"] for c in changes)
        return total_changes / len(changes) if changes else 0.0
    
    def get_high_churn_files(self, threshold: float = 50.0) -> List[str]:
        """Get files with high churn rates"""
        high_churn = []
        for file_path in self.file_changes:
            if self.get_churn_rate(file_path) > threshold:
                high_churn.append(file_path)
        return high_churn


def calculate_maintainability_index(
    halstead_volume: float,
    cyclomatic_complexity: int,
    lines_of_code: int
) -> float:
    """
    Calculate maintainability index.
    
    MI = 171 - 5.2 * ln(V) - 0.23 * G - 16.2 * ln(LOC)
    Normalized to 0-100 scale.
    """
    if halstead_volume <= 0 or lines_of_code <= 0:
        return 100.0
    
    mi = 171 - 5.2 * math.log(halstead_volume) \
           - 0.23 * cyclomatic_complexity \
           - 16.2 * math.log(lines_of_code)
    
    # Normalize to 0-100
    mi = max(0, min(100, mi * 100 / 171))
    
    return mi
