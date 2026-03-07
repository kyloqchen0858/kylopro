#!/usr/bin/env python3
"""
向量记忆库安装脚本
安装依赖并初始化配置
"""

import subprocess
import sys
from pathlib import Path


def check_python_version():
    """检查Python版本"""
    print("检查Python版本...")
    
    if sys.version_info < (3, 8):
        print(f"❌ Python版本过低: {sys.version}")
        print("  需要 Python 3.8 或更高版本")
        return False
    
    print(f"✅ Python版本: {sys.version}")
    return True


def install_dependencies():
    """安装依赖"""
    print("\n安装向量记忆库依赖...")
    
    dependencies = [
        "chromadb>=0.4.22",  # 向量数据库
        "sentence-transformers>=2.2.2",  # 本地嵌入模型
        "numpy>=1.24.0",  # 数值计算
        "pydantic>=2.0.0",  # 数据验证
        "ollama>=0.1.0",  # Ollama API（可选）
        "faiss-cpu>=1.7.0",  # FAISS向量搜索（可选）
    ]
    
    try:
        # 使用pip安装
        for dep in dependencies:
            print(f"安装 {dep}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", dep],
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                print(f"✅ {dep} 安装成功")
            else:
                print(f"⚠️ {dep} 安装失败: {result.stderr[:100]}")
        
        return True
        
    except Exception as e:
        print(f"❌ 依赖安装失败: {e}")
        return False


def create_config_files():
    """创建配置文件"""
    print("\n创建配置文件...")
    
    config_dir = Path(__file__).parent.parent.parent / "config"
    config_dir.mkdir(exist_ok=True)
    
    # 向量记忆库配置
    vector_memory_config = """# 向量记忆库配置
vector_memory:
  # 数据库配置
  db_type: "chromadb"  # chromadb, faiss, memory
  persist_path: "./data/memory"
  collection_name: "kylopro_memories"
  max_memories: 10000
  
  # ChromaDB特定配置
  chromadb:
    host: "localhost"
    port: 8000
    persist_directory: "./data/memory/chromadb"
    
  # 嵌入模型配置
  embedding:
    model_type: "local"  # local, ollama, openai, cohere
    
    # 本地模型配置
    local:
      model_name: "BAAI/bge-small-zh-v1.5"
      device: "cpu"  # cpu, cuda
      
    # Ollama配置
    ollama:
      model: "nomic-embed-text"
      base_url: "http://localhost:11434"
      
    # OpenAI配置
    openai:
      model: "text-embedding-3-small"
      api_key: "${OPENAI_API_KEY}"
      
  # 记忆管理配置
  memory_management:
    cleanup_threshold: 0.8  # 达到80%容量时清理
    ttl_days: 30  # 记忆默认保存30天
    importance_threshold: 0.3  # 重要性低于0.3的记忆可能被清理
    
  # 性能配置
  performance:
    batch_size: 100
    cache_size: 1000
    cache_ttl: 3600  # 缓存1小时
"""
    
    config_file = config_dir / "vector_memory.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(vector_memory_config)
    
    print(f"✅ 配置文件创建: {config_file}")
    
    # 创建环境变量示例
    env_example = """# 向量记忆库环境变量
VECTOR_MEMORY_DB_TYPE=chromadb
VECTOR_MEMORY_PERSIST_PATH=./data/memory
VECTOR_MEMORY_EMBEDDING_MODEL=local

# OpenAI配置（如果使用）
OPENAI_API_KEY=your_openai_api_key_here

# Cohere配置（如果使用）
COHERE_API_KEY=your_cohere_api_key_here

# Ollama配置
OLLAMA_BASE_URL=http://localhost:11434
"""
    
    env_file = config_dir / ".env.vector_memory"
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_example)
    
    print(f"✅ 环境变量示例创建: {env_file}")
    
    return True


def create_data_directories():
    """创建数据目录"""
    print("\n创建数据目录...")
    
    base_dir = Path(__file__).parent.parent.parent
    data_dirs = [
        "data/memory",
        "data/memory/chromadb",
        "data/memory/exports",
        "logs/vector_memory",
    ]
    
    for dir_path in data_dirs:
        full_path = base_dir / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ 创建目录: {full_path}")
    
    return True


def create_test_script():
    """创建测试脚本"""
    print("\n创建测试脚本...")
    
    test_script = """#!/usr/bin/env python3
"""
    
    # 复制examples/basic_usage.py作为测试脚本
    examples_dir = Path(__file__).parent / "examples"
    test_file = Path(__file__).parent.parent.parent / "test_vector_memory.py"
    
    if (examples_dir / "basic_usage.py").exists():
        with open(examples_dir / "basic_usage.py", "r", encoding="utf-8") as f:
            test_content = f.read()
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)
        
        # 使脚本可执行
        test_file.chmod(0o755)
        print(f"✅ 测试脚本创建: {test_file}")
    
    return True


def print_usage_instructions():
    """打印使用说明"""
    print("\n" + "="*60)
    print("向量记忆库安装完成!")
    print("="*60)
    
    print("\n📚 使用说明:")
    
    print("\n1. 基本使用:")
    print("   from skills.vector_memory.memory import VectorMemory")
    print("   memory = VectorMemory()")
    print("   await memory.initialize()")
    print("   await memory.store('记忆内容', importance=0.8)")
    print("   results = await memory.search('查询', limit=5)")
    
    print("\n2. 命令行工具:")
    print("   # 初始化")
    print("   python -m skills.vector_memory.cli init --db chromadb --model local")
    print("   ")
    print("   # 存储记忆")
    print("   python -m skills.vector_memory.cli store --content '记忆内容'")
    print("   ")
    print("   # 搜索记忆")
    print("   python -m skills.vector_memory.cli search --query 'AI助手'")
    print("   ")
    print("   # 获取统计")
    print("   python -m skills.vector_memory.cli stats")
    
    print("\n3. 集成到Kylopro:")
    print("   修改 core/provider.py，添加向量记忆库支持")
    print("   在响应时自动注入相关记忆上下文")
    
    print("\n4. 测试:")
    print("   python test_vector_memory.py")
    print("   python -m skills.vector_memory.cli test")
    
    print("\n5. 生产部署:")
    print("   - 使用ChromaDB作为生产数据库")
    print("   - 配置本地嵌入模型（BGE-small-zh）")
    print("   - 设置定期备份和清理")
    
    print("\n🔧 配置位置:")
    print("   - 主配置: config/vector_memory.yaml")
    print("   - 环境变量: config/.env.vector_memory")
    print("   - 数据目录: data/memory/")
    print("   - 日志目录: logs/vector_memory/")
    
    print("\n⚠️ 注意事项:")
    print("   - 首次使用需要下载嵌入模型（约100MB）")
    print("   - 生产环境建议使用GPU加速嵌入计算")
    print("   - 定期备份记忆数据")
    
    print("\n🚀 下一步:")
    print("   1. 运行测试脚本验证安装")
    print("   2. 集成到Kylopro核心")
    print("   3. 配置自动记忆管理")
    print("   4. 添加记忆可视化界面")


def main():
    """主安装函数"""
    print("向量记忆库安装脚本")
    print("="*60)
    
    # 检查Python版本
    if not check_python_version():
        return 1
    
    # 安装依赖
    if not install_dependencies():
        print("⚠️ 依赖安装有警告，但继续安装...")
    
    # 创建配置文件
    if not create_config_files():
        return 1
    
    # 创建数据目录
    if not create_data_directories():
        return 1
    
    # 创建测试脚本
    if not create_test_script():
        return 1
    
    # 打印使用说明
    print_usage_instructions()
    
    print("\n✅ 安装完成!")
    return 0


if __name__ == "__main__":
    sys.exit(main())