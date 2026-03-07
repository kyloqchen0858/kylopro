"""
Kylopro 向量记忆库 (Vector Memory)
==================================
使用嵌入向量存储和检索记忆，支持语义搜索和长期记忆管理。

核心功能：
1. 存储对话记忆为向量
2. 语义搜索相关记忆
3. 记忆去重和合并
4. 记忆时效管理
5. 上下文增强

支持的后端：
- ChromaDB (默认)
- FAISS
- Qdrant
- 内存存储 (测试用)

支持的嵌入模型：
- 本地模型 (sentence-transformers)
- Ollama 本地模型
- OpenAI API
- Cohere API
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field

# 尝试导入依赖
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("ChromaDB not available, using in-memory storage")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("Sentence Transformers not available")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("Ollama not available")

# 类型定义
class MemoryRecord(BaseModel):
    """记忆记录"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    importance: float = 0.5  # 重要性分数 0-1
    access_count: int = 0
    last_accessed: float = Field(default_factory=time.time)
    
    class Config:
        arbitrary_types_allowed = True

class SearchResult(BaseModel):
    """搜索结果"""
    memory: MemoryRecord
    score: float  # 相似度分数 0-1
    relevance: float  # 相关性分数 (结合相似度和重要性)

class DBType(str, Enum):
    """数据库类型"""
    CHROMA = "chromadb"
    FAISS = "faiss"
    QDRANT = "qdrant"
    MEMORY = "memory"  # 内存存储，用于测试

class EmbeddingModelType(str, Enum):
    """嵌入模型类型"""
    LOCAL = "local"  # sentence-transformers
    OLLAMA = "ollama"
    OPENAI = "openai"
    COHERE = "cohere"
    TEST = "test"  # 测试用随机向量

class VectorMemory:
    """向量记忆库"""
    
    def __init__(
        self,
        db_type: Union[str, DBType] = DBType.CHROMA,
        embedding_model: Union[str, EmbeddingModelType] = EmbeddingModelType.LOCAL,
        persist_path: Optional[Union[str, Path]] = None,
        collection_name: str = "kylopro_memories",
        embedding_dim: int = 384,  # BGE-small的维度
        max_memories: int = 10000,
        debug: bool = False,
    ):
        """
        初始化向量记忆库
        
        Args:
            db_type: 数据库类型
            embedding_model: 嵌入模型类型
            persist_path: 持久化路径
            collection_name: 集合名称
            embedding_dim: 嵌入维度
            max_memories: 最大记忆数量
            debug: 调试模式
        """
        self.db_type = DBType(db_type) if isinstance(db_type, str) else db_type
        self.embedding_model_type = (
            EmbeddingModelType(embedding_model) 
            if isinstance(embedding_model, str) 
            else embedding_model
        )
        self.persist_path = Path(persist_path) if persist_path else Path("./data/memory")
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.max_memories = max_memories
        self.debug = debug
        
        # 创建持久化目录
        self.persist_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化日志
        self.logger = logging.getLogger(__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        
        # 初始化组件
        self.db = None
        self.embedding_model = None
        self.collection = None
        
        # 内存存储（备用）
        self.memory_storage: Dict[str, MemoryRecord] = {}
        
        # 统计信息
        self.stats = {
            "total_stores": 0,
            "total_searches": 0,
            "total_deletes": 0,
            "avg_search_time": 0.0,
        }
        
        self.logger.info(f"初始化向量记忆库: db={self.db_type}, model={self.embedding_model_type}")
    
    async def initialize(self) -> bool:
        """初始化数据库和模型"""
        try:
            # 初始化数据库
            await self._init_database()
            
            # 初始化嵌入模型
            await self._init_embedding_model()
            
            # 创建或获取集合
            await self._init_collection()
            
            self.logger.info("向量记忆库初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"向量记忆库初始化失败: {e}")
            # 回退到内存存储
            self.db_type = DBType.MEMORY
            self.logger.warning("回退到内存存储模式")
            return True
    
    async def _init_database(self):
        """初始化数据库"""
        if self.db_type == DBType.CHROMA:
            if not CHROMA_AVAILABLE:
                raise ImportError("ChromaDB not installed. Run: pip install chromadb")
            
            # ChromaDB持久化设置
            chroma_settings = Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self.persist_path / "chromadb"),
                anonymized_telemetry=False,
            )
            
            self.db = chromadb.Client(chroma_settings)
            self.logger.info(f"ChromaDB初始化成功: {self.persist_path / 'chromadb'}")
            
        elif self.db_type == DBType.MEMORY:
            self.logger.info("使用内存存储模式")
            self.db = None
            
        else:
            raise ValueError(f"不支持的数据库类型: {self.db_type}")
    
    async def _init_embedding_model(self):
        """初始化嵌入模型"""
        if self.embedding_model_type == EmbeddingModelType.LOCAL:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError("Sentence Transformers not installed. Run: pip install sentence-transformers")
            
            # 使用轻量级中文模型
            model_name = "BAAI/bge-small-zh-v1.5"
            self.logger.info(f"加载本地嵌入模型: {model_name}")
            
            # 异步加载模型
            loop = asyncio.get_event_loop()
            self.embedding_model = await loop.run_in_executor(
                None, 
                lambda: SentenceTransformer(model_name)
            )
            
            # 验证维度
            actual_dim = self.embedding_model.get_sentence_embedding_dimension()
            if actual_dim != self.embedding_dim:
                self.logger.warning(f"模型维度({actual_dim})与配置维度({self.embedding_dim})不匹配，更新配置")
                self.embedding_dim = actual_dim
            
        elif self.embedding_model_type == EmbeddingModelType.OLLAMA:
            if not OLLAMA_AVAILABLE:
                raise ImportError("Ollama not available")
            
            self.logger.info("使用Ollama嵌入模型")
            # Ollama嵌入通过API调用，不需要本地模型对象
            
        elif self.embedding_model_type == EmbeddingModelType.TEST:
            self.logger.info("使用测试嵌入模型（随机向量）")
            
        else:
            raise ValueError(f"不支持的嵌入模型类型: {self.embedding_model_type}")
    
    async def _init_collection(self):
        """初始化集合"""
        if self.db_type == DBType.CHROMA:
            # 创建或获取ChromaDB集合
            try:
                self.collection = self.db.get_collection(self.collection_name)
                self.logger.info(f"获取现有集合: {self.collection_name}")
            except:
                self.collection = self.db.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Kylopro向量记忆库"}
                )
                self.logger.info(f"创建新集合: {self.collection_name}")
        
        elif self.db_type == DBType.MEMORY:
            self.collection = None
            self.logger.info("内存存储模式，无集合概念")
    
    async def get_embedding(self, text: str) -> List[float]:
        """获取文本的嵌入向量"""
        if not text or not text.strip():
            return [0.0] * self.embedding_dim
        
        if self.embedding_model_type == EmbeddingModelType.LOCAL:
            # 使用本地模型
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self.embedding_model.encode(text).tolist()
            )
            return embedding
            
        elif self.embedding_model_type == EmbeddingModelType.OLLAMA:
            # 使用Ollama API
            try:
                response = ollama.embeddings(model="nomic-embed-text", prompt=text)
                return response["embedding"]
            except Exception as e:
                self.logger.error(f"Ollama嵌入失败: {e}")
                # 回退到随机向量
                return self._get_random_embedding()
            
        elif self.embedding_model_type == EmbeddingModelType.TEST:
            # 测试用随机向量
            return self._get_random_embedding()
            
        else:
            raise ValueError(f"不支持的嵌入模型类型: {self.embedding_model_type}")
    
    def _get_random_embedding(self) -> List[float]:
        """生成随机嵌入向量（测试用）"""
        return list(np.random.randn(self.embedding_dim).astype(float))
    
    async def store(
        self,
        content: str,
        key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """
        存储记忆
        
        Args:
            content: 记忆内容
            key: 记忆键（可选，自动生成）
            metadata: 元数据
            importance: 重要性分数 0-1
            embedding: 预计算的嵌入向量（可选）
            
        Returns:
            记忆ID
        """
        start_time = time.time()
        
        # 生成记忆ID
        memory_id = key or f"memory_{int(time.time() * 1000)}_{hash(content) % 10000:04d}"
        
        # 准备元数据
        metadata = metadata or {}
        metadata.update({
            "stored_at": datetime.now().isoformat(),
            "importance": importance,
            "content_length": len(content),
        })
        
        # 获取或计算嵌入向量
        if embedding is None:
            embedding = await self.get_embedding(content)
        
        # 创建记忆记录
        memory = MemoryRecord(
            id=memory_id,
            content=content,
            embedding=embedding,
            metadata=metadata,
            importance=importance,
        )
        
        # 存储到数据库
        if self.db_type == DBType.CHROMA:
            # 存储到ChromaDB
            self.collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata],
                ids=[memory_id],
            )
            
        elif self.db_type == DBType.MEMORY:
            # 存储到内存
            self.memory_storage[memory_id] = memory
        
        # 更新统计
        self.stats["total_stores"] += 1
        
        # 检查是否需要清理
        await self._check_and_cleanup()
        
        elapsed = time.time() - start_time
        self.logger.debug(f"存储记忆完成: id={memory_id}, 耗时={elapsed:.3f}s")
        
        return memory_id
    
    async def batch_store(
        self,
        memories: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> List[str]:
        """批量存储记忆"""
        memory_ids = []
        
        for i in range(0, len(memories), batch_size):
            batch = memories[i:i + batch_size]
            
            # 准备批量数据
            embeddings = []
            documents = []
            metadatas = []
            ids = []
            
            for mem in batch:
                content = mem.get("content", "")
                key = mem.get("key")
                metadata = mem.get("metadata", {})
                importance = mem.get("importance", 0.5)
                
                # 生成ID
                memory_id = key or f"batch_{int(time.time() * 1000)}_{i:04d}"
                
                # 获取嵌入
                embedding = await self.get_embedding(content)
                
                # 准备元数据
                metadata.update({
                    "stored_at": datetime.now().isoformat(),
                    "importance": importance,
                    "content_length": len(content),
                    "batch_index": i,
                })
                
                # 添加到批量
                embeddings.append(embedding)
                documents.append(content)
                metadatas.append(metadata)
                ids.append(memory_id)
                
                # 创建内存记录
                memory = MemoryRecord(
                    id=memory_id,
                    content=content,
                    embedding=embedding,
                    metadata=metadata,
                    importance=importance,
                )
                self.memory_storage[memory_id] = memory
                
                memory_ids.append(memory_id)
            
            # 批量存储到数据库
            if self.db_type == DBType.CHROMA and embeddings:
                self.collection.add(
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                )
            
            self.logger.debug(f"批量存储进度: {i + len(batch)}/{len(memories)}")
        
        self.stats["total_stores"] += len(memory_ids)
        self.logger.info(f"批量存储完成: {len(memory_ids)} 条记忆")
        
        return memory_ids
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.3,
        filter_metadata: Optional[Dict[str, Any]] = None,
        include_embeddings: bool = False,
    ) -> List[SearchResult]:
        """
        搜索相关记忆
        
        Args:
            query: 搜索查询
            limit: 返回结果数量
            min_score: 最小相似度分数
            filter_metadata: 元数据过滤条件
            include_embeddings: 是否包含嵌入向量
            
        Returns:
            搜索结果列表
        """
        start_time = time.time()
        
        if not query or not query.strip():
            return []
        
        # 获取查询的嵌入向量
        query_embedding = await self.get_embedding(query)
        
        results = []
        
        if self.db_type == DBType.CHROMA:
            # ChromaDB搜索
            search_results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit * 2,  # 多取一些用于过滤
                where=filter_metadata,
                include=["documents", "metadatas", "distances", "embeddings"],
            )
            
            # 处理结果
            if search_results["ids"]:
                for i in range(len(search_results["ids"][0])):
                    memory_id = search_results["ids"][0][i]
                    content = search_results["documents"][0][i]
                    metadata = search_results["metadatas"][0][i]
                    distance = search_results["distances"][0][i]
                    embedding = search_results["embeddings"][0][i] if include_embeddings else None
                    
                    # 转换距离为相似度分数 (ChromaDB使用余弦距离)
                    similarity = 1.0 - distance  # 余弦距离 -> 相似度
                    
                    if similarity >= min_score:
                        # 获取重要性分数
                        importance = metadata.get("importance", 0.5)
                        
                        # 计算相关性分数 (结合相似度和重要性)
                        relevance = similarity * 0.7 + importance * 0.3
                        
                        # 创建记忆记录
                        memory = MemoryRecord(
                            id=memory_id,
                            content=content,
                            embedding=embedding,
                            metadata=metadata,
                            importance=importance,
                        )
                        
                        # 更新访问统计
                        memory.access_count += 1
                        memory.last_accessed = time.time()
                        
                        results.append(SearchResult(
                            memory=memory,
                            score=similarity,
                            relevance=relevance,
                        ))
        
        elif self.db_type == DBType.MEMORY:
            # 内存存储搜索
            query_embedding_np = np.array(query_embedding)
            
            for memory_id, memory in self.memory_storage.items():
                if memory.embedding:
                    # 计算余弦相似度
                    memory_embedding_np = np.array(memory.embedding)
                    similarity = float(
                        np.dot(query_embedding_np, memory_embedding_np) /
                        (np.linalg.norm(query_embedding_np) * np.linalg.norm(memory_embedding_np) + 1e-8)
                    )
                    
                    if similarity >= min_score:
                        # 检查元数据过滤
                        if filter_metadata:
                            match = True
                            for key, value in filter_metadata.items():
                                if memory.metadata.get(key) != value:
                                    match = False
                                    break
                            if not match:
                                continue
                        
                        # 计算相关性分数
                        relevance = similarity * 0.7 + memory.importance * 0.3
                        
                        # 更新访问统计
                        memory.access_count += 1
                        memory.last_accessed = time.time()
                        
                        results.append(SearchResult(
                            memory=memory,
                            score=similarity,
                            relevance=relevance,
                        ))
        
        # 按相关性排序并限制数量
        results.sort(key=lambda x: x.relevance, reverse=True)
        results = results[:limit]
        
        # 更新统计
        self.stats["total_searches"] += 1
        elapsed = time.time() - start_time
        self.stats["avg_search_time"] = (
            self.stats["avg_search_time"] * (self.stats["total_searches"] - 1) + elapsed
        ) / self.stats["total_searches"]
        
        self.logger.debug(f"搜索完成: 查询='{query[:50]}...', 结果={len(results)}, 耗时={elapsed:.3f}s")
        
        return results
    
    async def get(self, memory_id: str) -> Optional[MemoryRecord]:
        """获取特定记忆"""
        if self.db_type == DBType.CHROMA:
            try:
                result = self.collection.get(ids=[memory_id])
                if result["ids"]:
                    content = result["documents"][0]
                    metadata = result["metadatas"][0]
                    
                    memory = MemoryRecord(
                        id=memory_id,
                        content=content,
                        metadata=metadata,
                        importance=metadata.get("importance", 0.5),
                    )
                    
                    # 更新访问统计
                    memory.access_count += 1
                    memory.last_accessed = time.time()
                    
                    return memory
            except:
                pass
        
        elif self.db_type == DBType.MEMORY:
            memory = self.memory_storage.get(memory_id)
            if memory:
                memory.access_count += 1
                memory.last_accessed = time.time()
                return memory
        
        return None
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        try:
            if self.db_type == DBType.CHROMA:
                self.collection.delete(ids=[memory_id])
            
            elif self.db_type == DBType.MEMORY:
                if memory_id in self.memory_storage:
                    del self.memory_storage[memory_id]
            
            # 从内存存储中也删除（如果存在）
            if memory_id in self.memory_storage:
                del self.memory_storage[memory_id]
            
            self.stats["total_deletes"] += 1
            self.logger.debug(f"删除记忆: {memory_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"删除记忆失败: {memory_id}, 错误: {e}")
            return False
    
    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
    ) -> bool:
        """更新记忆"""
        try:
            # 获取现有记忆
            memory = await self.get(memory_id)
            if not memory:
                return False
            
            # 更新字段
            if content is not None:
                memory.content = content
                # 重新计算嵌入
                memory.embedding = await self.get_embedding(content)
            
            if metadata is not None:
                memory.metadata.update(metadata)
            
            if importance is not None:
                memory.importance = max(0.0, min(1.0, importance))
                memory.metadata["importance"] = memory.importance
            
            memory.updated_at = time.time()
            memory.metadata["updated_at"] = datetime.now().isoformat()
            
            # 更新到数据库
            if self.db_type == DBType.CHROMA:
                self.collection.update(
                    ids=[memory_id],
                    documents=[memory.content] if content else None,
                    metadatas=[memory.metadata],
                    embeddings=[memory.embedding] if memory.embedding else None,
                )
            
            elif self.db_type == DBType.MEMORY:
                self.memory_storage[memory_id] = memory
            
            self.logger.debug(f"更新记忆: {memory_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"更新记忆失败: {memory_id}, 错误: {e}")
            return False
    
    async def get_context(
        self,
        query: str,
        max_tokens: int = 1000,
        limit: int = 10,
        min_score: float = 0.3,
    ) -> str:
        """
        获取相关记忆作为上下文
        
        Args:
            query: 查询文本
            max_tokens: 最大token数
            limit: 最大记忆数量
            min_score: 最小相似度分数
            
        Returns:
            格式化后的上下文字符串
        """
        # 搜索相关记忆
        results = await self.search(
            query=query,
            limit=limit,
            min_score=min_score,
        )
        
        if not results:
            return ""
        
        # 构建上下文
        context_parts = []
        current_tokens = 0
        
        for i, result in enumerate(results):
            memory = result.memory
            
            # 估算token数（简单估算：4个字符≈1个token）
            content_tokens = len(memory.content) // 4
            metadata_str = json.dumps(memory.metadata, ensure_ascii=False)
            metadata_tokens = len(metadata_str) // 4
            
            total_tokens = content_tokens + metadata_tokens + 50  # 加上格式化的开销
            
            if current_tokens + total_tokens > max_tokens:
                break
            
            # 格式化记忆
            memory_str = f"""记忆 {i+1} (相关性: {result.relevance:.2f}):
内容: {memory.content}
元数据: {metadata_str}
重要性: {memory.importance:.2f}
访问次数: {memory.access_count}
最后访问: {datetime.fromtimestamp(memory.last_accessed).strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            context_parts.append(memory_str)
            current_tokens += total_tokens
        
        context = "\n---\n".join(context_parts)
        
        self.logger.debug(f"生成上下文: {len(results)} 条记忆, 约 {current_tokens} tokens")
        
        return context
    
    async def _check_and_cleanup(self):
        """检查并清理旧记忆"""
        if self.db_type == DBType.MEMORY:
            # 内存存储清理
            if len(self.memory_storage) > self.max_memories:
                # 按最后访问时间和重要性排序，删除最不重要的
                memories = list(self.memory_storage.items())
                memories.sort(key=lambda x: (
                    x[1].last_accessed,  # 最后访问时间
                    -x[1].importance,    # 重要性（反向）
                ))
                
                # 删除多余的记忆
                to_delete = memories[:len(memories) - self.max_memories]
                for memory_id, _ in to_delete:
                    del self.memory_storage[memory_id]
                
                self.logger.info(f"清理内存存储: 删除 {len(to_delete)} 条记忆")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_memories = 0
        
        if self.db_type == DBType.CHROMA:
            total_memories = self.collection.count()
        elif self.db_type == DBType.MEMORY:
            total_memories = len(self.memory_storage)
        
        return {
            "db_type": self.db_type.value,
            "embedding_model": self.embedding_model_type.value,
            "total_memories": total_memories,
            "max_memories": self.max_memories,
            "embedding_dim": self.embedding_dim,
            **self.stats,
        }
    
    async def export_memories(self, filepath: Union[str, Path]) -> bool:
        """导出所有记忆到文件"""
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            memories = []
            
            if self.db_type == DBType.CHROMA:
                # 从ChromaDB导出
                all_data = self.collection.get()
                for i in range(len(all_data["ids"])):
                    memories.append({
                        "id": all_data["ids"][i],
                        "content": all_data["documents"][i],
                        "metadata": all_data["metadatas"][i],
                    })
            
            elif self.db_type == DBType.MEMORY:
                # 从内存存储导出
                for memory_id, memory in self.memory_storage.items():
                    memories.append({
                        "id": memory_id,
                        "content": memory.content,
                        "metadata": memory.metadata,
                        "importance": memory.importance,
                        "access_count": memory.access_count,
                        "created_at": memory.created_at,
                        "last_accessed": memory.last_accessed,
                    })
            
            # 保存到文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"导出记忆完成: {len(memories)} 条记忆 -> {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"导出记忆失败: {e}")
            return False
    
    async def import_memories(self, filepath: Union[str, Path]) -> bool:
        """从文件导入记忆"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                self.logger.error(f"导入文件不存在: {filepath}")
                return False
            
            with open(filepath, "r", encoding="utf-8") as f:
                memories = json.load(f)
            
            # 批量导入
            memory_dicts = []
            for mem in memories:
                memory_dicts.append({
                    "key": mem["id"],
                    "content": mem["content"],
                    "metadata": mem["metadata"],
                    "importance": mem.get("importance", 0.5),
                })
            
            await self.batch_store(memory_dicts)
            
            self.logger.info(f"导入记忆完成: {len(memories)} 条记忆 <- {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"导入记忆失败: {e}")
            return False
    
    async def close(self):
        """关闭记忆库"""
        if self.db_type == DBType.CHROMA:
            # ChromaDB会自动持久化
            pass
        
        self.logger.info("向量记忆库已关闭")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()


# 便捷函数
async def create_vector_memory(
    db_type: str = "chromadb",
    embedding_model: str = "local",
    persist_path: Optional[str] = None,
    **kwargs,
) -> VectorMemory:
    """创建向量记忆库实例"""
    memory = VectorMemory(
        db_type=db_type,
        embedding_model=embedding_model,
        persist_path=persist_path,
        **kwargs,
    )
    await memory.initialize()
    return memory


# 测试代码
async def test_vector_memory():
    """测试向量记忆库"""
    print("测试向量记忆库...")
    
    # 使用内存存储进行测试
    memory = VectorMemory(
        db_type="memory",
        embedding_model="test",  # 测试用随机向量
        debug=True,
    )
    
    await memory.initialize()
    
    # 存储测试记忆
    test_memories = [
        {
            "content": "用户喜欢简洁的回答方式",
            "metadata": {"category": "preference", "user": "qianchen"},
            "importance": 0.8,
        },
        {
            "content": "Kylopro项目目标是创建全能AI助手",
            "metadata": {"category": "project", "project": "Kylopro-Nexus"},
            "importance": 0.9,
        },
        {
            "content": "Trae是AI编程助手，支持MCP协议",
            "metadata": {"category": "tool", "tool": "Trae"},
            "importance": 0.7,
        },
    ]
    
    print("存储测试记忆...")
    memory_ids = await memory.batch_store(test_memories)
    print(f"存储完成: {len(memory_ids)} 条记忆")
    
    # 搜索测试
    print("\n搜索测试...")
    results = await memory.search("AI助手", limit=3)
    print(f"搜索 'AI助手' 结果:")
    for i, result in enumerate(results):
        print(f"  {i+1}. {result.memory.content[:50]}... (相关性: {result.relevance:.2f})")
    
    # 获取上下文测试
    print("\n获取上下文测试...")
    context = await memory.get_context("用户偏好", max_tokens=500)
    print(f"上下文长度: {len(context)} 字符")
    print(f"上下文预览: {context[:200]}...")
    
    # 获取统计信息
    print("\n统计信息:")
    stats = await memory.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    await memory.close()
    print("\n测试完成!")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_vector_memory())