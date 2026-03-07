# 开发任务：改进类型注解并添加单元测试

## 需求描述
根据代码审查结果，改进Kylopro-Nexus项目的类型注解，并为核心模块添加单元测试，提升代码质量和可维护性。

## 具体任务

### 任务1：运行静态类型检查
- 安装mypy：`pip install mypy`
- 运行mypy检查整个项目：`mypy core/ skills/ --ignore-missing-imports`
- 记录所有类型错误和警告

### 任务2：修复类型注解问题
- 修改文件：`core/provider.py`
  - 为函数 `_load_nanobot_config()` 添加返回类型注解
  - 为 `PROVIDER_SLOTS` 字典添加具体类型
  - 修复 `_safety_check()` 方法的参数类型
- 修改文件：`core/engine.py`
  - 为 `main_loop()` 添加返回类型
  - 为 `_handle_command()` 的参数添加类型注解
- 修改文件：`skills/telegram_notify/notify.py`
  - 为 `send_notification()` 添加参数和返回类型
- 修改其他技能文件中的类型注解

### 任务3：添加单元测试
- 创建测试目录结构：`tests/core/`, `tests/skills/`
- 编写 `tests/core/test_provider.py`：
  - 测试 `provider.py` 中的配置加载
  - 测试双核路由切换逻辑
  - 模拟API错误处理
- 编写 `tests/core/test_engine.py`：
  - 测试 `engine.py` 的主循环基本流程
  - 测试命令解析功能
- 编写 `tests/skills/test_telegram_notify.py`：
  - 测试通知发送函数（模拟实际发送）
- 使用 `pytest` 和 `pytest-asyncio` 进行异步测试

### 任务4：完善依赖管理
- 冻结当前依赖版本：`pip freeze > requirements.txt`
- 创建开发依赖文件：`requirements-dev.txt`，包含：
  - mypy
  - pytest
  - pytest-asyncio
  - black (代码格式化)
- 更新 `setup.bat` 以同时安装开发依赖

### 任务5：配置持续集成检查
- 创建 `.github/workflows/test.yml` 用于GitHub Actions
  - 运行mypy静态检查
  - 运行pytest单元测试
  - 检查代码格式（black）
- 确保CI在Windows和Linux环境下都能通过

## 技术细节

### 类型注解标准
- 使用Python 3.10+的类型注解语法（`|` 联合类型）
- 复杂类型使用 `typing` 模块（`Dict`, `List`, `Optional`, `Any` 等）
- 为所有公共函数和方法添加完整的类型注解

### 测试策略
- 单元测试注重隔离，使用mock替换外部依赖（如API调用）
- 集成测试验证模块间协作
- 测试覆盖率目标：核心模块达到80%以上

### 工具配置
- 创建 `pyproject.toml` 统一配置工具：
  ```toml
  [tool.mypy]
  python_version = "3.10"
  ignore_missing_imports = true
  
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  ```

## 预期结果
1. ✅ mypy检查通过，无类型错误
2. ✅ 所有核心函数都有完整的类型注解
3. ✅ 单元测试覆盖核心功能，通过率100%
4. ✅ 开发依赖明确，便于团队协作
5. ✅ CI流水线配置完成，自动运行检查

## 优先级
高 - 提升代码质量和可维护性

## 测试验证
任务完成后，运行以下验证：
1. `mypy core/ skills/` - 应无错误输出
2. `pytest tests/ -v` - 所有测试通过
3. 检查CI运行结果 - 绿色通过状态

## 备注
此任务有助于建立项目的质量标准，为后续开发奠定基础。