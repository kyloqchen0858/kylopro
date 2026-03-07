---
name: vector_memory
description: 向量记忆库 - 使用嵌入向量存储和检索记忆，支持语义搜索和长期记忆管理
always: false
---

# 🌟 Kylopro 新技能：[向量记忆库 (Vector Memory)]

## ⚙️ 这个技能能做什么？

我将拥有长期记忆能力，不再每次对话都从零开始。通过向量嵌入技术，我可以：
1. **存储对话记忆** - 将重要对话转换为向量存储
2. **语义搜索记忆** - 根据语义相似度检索相关记忆
3. **记忆去重和合并** - 自动合并相似记忆
4. **记忆时效管理** - 根据时间衰减记忆权重
5. **上下文增强** - 在对话中自动注入相关记忆

## 🧩 技术架构

### 核心组件
1. **嵌入模型** - 使用本地模型或API将文本转换为向量
2. **向量数据库** - 存储和检索向量
3. **记忆管理器** - 管理记忆的生命周期
4. **搜索器** - 语义搜索和相关性排序

### 支持的向量数据库
- **ChromaDB** - 轻量级，易于部署
- **FAISS** - Facebook的高性能向量搜索
- **Qdrant** - 生产级向量数据库
- **Pinecone** - 云服务（需要API）
- **Weaviate** - 开源向量搜索引擎

### 嵌入模型选项
- **本地模型** - sentence-transformers, BGE, etc.
- **API模型** - OpenAI, Cohere, HuggingFace
- **Ollama模型** - 本地运行的嵌入模型

## 💡 使用场景

### 1. 对话记忆
```python
# 存储当前对话的重要信息
await memory.store("用户偏好", "用户喜欢简洁的回答方式", metadata={"timestamp": "2026-03-07"})
```

### 2. 项目上下文记忆
```python
# 存储项目相关信息
await memory.store("Kylopro项目", "项目目标是创建全能AI助手", metadata={"project": "Kylopro-Nexus"})
```

### 3. 技能使用记忆
```python
# 记录技能使用情况
await memory.store("IDE桥接技能", "用户经常使用IDE桥接与Trae协同开发", metadata={"skill": "ide_bridge"})
```

### 4. 语义搜索记忆
```python
# 搜索相关记忆
results = await memory.search("如何与Trae协同", limit=5)
for result in results:
    print(f"相关性: {result.score:.2f} - {result.content}")
```

## 🚀 使用方法

### 基本使用
```python
from skills.vector_memory.memory import VectorMemory

# 初始化记忆库
memory = VectorMemory(
    db_type="chromadb",  # 或 "faiss", "qdrant"
    embedding_model="local",  # 或 "openai", "cohere"
    persist_path="./data/memory"
)

# 存储记忆
await memory.store(
    key="用户偏好",
    content="用户喜欢简洁的回答方式",
    metadata={"category": "preference", "importance": 0.8}
)

# 搜索记忆
results = await memory.search("简洁回答", limit=3)

# 获取相关上下文
context = await memory.get_context("用户偏好", max_tokens=500)
```

### 集成到Kylopro核心
```python
# 在provider.py中集成
class EnhancedProvider:
    def __init__(self):
        self.memory = VectorMemory()
    
    async def get_relevant_memories(self, query: str) -> str:
        """获取相关记忆作为上下文"""
        results = await self.memory.search(query, limit=5)
        context = "\n".join([f"- {r.content}" for r in results])
        return context
```

### 命令行工具
```bash
# 初始化记忆库
python -m skills.vector_memory.init --db chromadb --model local

# 存储记忆
python -m skills.vector_memory.store --key "项目目标" --content "创建全能AI助手"

# 搜索记忆
python -m skills.vector_memory.search --query "AI助手" --limit 5

# 统计记忆
python -m skills.vector_memory.stats
```

## 🔧 配置选项

### 数据库配置
```yaml
vector_memory:
  db_type: "chromadb"  # chromadb, faiss, qdrant
  persist_path: "./data/memory"
  collection_name: "kylopro_memories"
  
  # ChromaDB特定配置
  chromadb:
    host: "localhost"
    port: 8000
    
  # FAISS特定配置
  faiss:
    index_type: "IVF"  # IVF, Flat, HNSW
    nlist: 100
```

### 嵌入模型配置
```yaml
embedding:
  model_type: "local"  # local, openai, cohere, ollama
  
  # 本地模型
  local:
    model_name: "BAAI/bge-small-zh-v1.5"
    device: "cpu"  # cpu, cuda
    
  # OpenAI
  openai:
    model: "text-embedding-3-small"
    api_key: "${OPENAI_API_KEY}"
    
  # Ollama
  ollama:
    model: "nomic-embed-text"
    base_url: "http://localhost:11434"
```

### 记忆管理配置
```yaml
memory_management:
  max_memories: 10000
  cleanup_threshold: 0.8  # 达到80%容量时清理
  ttl_days: 30  # 记忆默认保存30天
  importance_threshold: 0.3  # 重要性低于0.3的记忆可能被清理
```

## 📊 性能优化

### 1. 批量操作
```python
# 批量存储提高性能
memories = [
    {"key": "pref1", "content": "内容1", "metadata": {...}},
    {"key": "pref2", "content": "内容2", "metadata": {...}},
]
await memory.batch_store(memories)
```

### 2. 缓存层
```python
# 添加LRU缓存
memory = VectorMemory(
    db_type="chromadb",
    cache_size=1000,  # 缓存1000个最近访问的记忆
    cache_ttl=3600  # 缓存1小时
)
```

### 3. 异步操作
```python
# 所有操作都是异步的
async with memory:
    await memory.store(...)
    results = await memory.search(...)
```

## 🛡️ 安全与隐私

### 1. 数据加密
- 所有记忆在存储前可加密
- 支持AES-256加密
- 密钥管理通过环境变量

### 2. 访问控制
- 基于角色的访问控制
- 记忆分类和权限管理
- 审计日志记录所有访问

### 3. 数据清理
- 自动清理过期记忆
- 手动删除特定记忆
- 导出和备份功能

## 🔍 监控与调试

### 1. 健康检查
```bash
python -m skills.vector_memory.health
```

### 2. 性能监控
```python
stats = await memory.get_stats()
print(f"记忆数量: {stats['total_memories']}")
print(f"存储大小: {stats['storage_size_mb']} MB")
print(f"平均搜索时间: {stats['avg_search_time_ms']} ms")
```

### 3. 调试模式
```python
memory = VectorMemory(debug=True)
# 启用详细日志
```

## 📈 扩展功能

### 1. 记忆图谱
```python
# 创建记忆之间的关系
await memory.link_memories("项目目标", "用户需求", relation="implements")
graph = await memory.get_memory_graph()
```

### 2. 记忆摘要
```python
# 自动生成记忆摘要
summary = await memory.summarize_memories(category="项目", max_tokens=200)
```

### 3. 记忆推荐
```python
# 基于当前上下文推荐相关记忆
recommendations = await memory.recommend(context="正在开发IDE桥接")
```

## 🚨 故障排除

### 常见问题
1. **数据库连接失败** - 检查端口和网络
2. **嵌入模型加载失败** - 检查模型路径和权限
3. **内存不足** - 调整缓存大小或使用磁盘存储
4. **搜索速度慢** - 优化索引或使用更快的模型

### 日志查看
```bash
tail -f logs/vector_memory.log
```

## 📚 参考资料

- [ChromaDB文档](https://docs.trychroma.com/)
- [FAISS文档](https://github.com/facebookresearch/faiss)
- [Sentence Transformers](https://www.sbert.net/)
- [向量搜索最佳实践](https://www.pinecone.io/learn/vector-search-best-practices/)

---

**安装状态**: 开发中（之前安装到一半消失，现在重新创建）
**优先级**: 高 - 记忆管理是Agent核心能力
**依赖**: chromadb, sentence-transformers, numpy