"""
Blackbird Search Engine Package
"""

__version__ = "1.0.0"
__author__ = "Blackbird Team"
__description__ = "A high-performance code search engine inspired by GitHub's Blackbird"

from .config import get_config, update_config

__all__ = [
    "__version__",
    "__author__",
    "__description__",
    "get_config",
    "update_config"
]
