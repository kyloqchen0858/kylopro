"""
向量记忆库技能
"""

from .memory import (
    VectorMemory,
    MemoryRecord,
    SearchResult,
    DBType,
    EmbeddingModelType,
    create_vector_memory,
)

__version__ = "1.0.0"
__all__ = [
    "VectorMemory",
    "MemoryRecord", 
    "SearchResult",
    "DBType",
    "EmbeddingModelType",
    "create_vector_memory",
]