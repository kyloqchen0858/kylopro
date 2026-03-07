# 开发任务：修复Kylopro编码问题

## 需求描述
修复Kylopro任务收件箱系统中的编码问题，确保在Windows环境下中文和特殊字符正常显示。

## 问题分析
1. **控制台输出乱码** - Windows控制台默认使用GBK编码，而Python使用UTF-8
2. **子进程输出丢失** - Python子进程输出未正确捕获
3. **文件读写编码** - 需要确保文件读写使用正确的编码

## 具体任务

### 任务1：创建编码修复工具
- 文件路径：`tools/encoding_fixer.py`
- 功能：提供统一的编码处理工具函数
- 包含：
  - `fix_console_output()` - 修复控制台输出编码
  - `safe_print()` - 安全的打印函数，自动处理编码
  - `run_command_with_encoding()` - 带编码处理的命令执行

### 任务2：修改任务收件箱代码
- 修改文件：`skills/task_inbox/inbox.py`
- 修改内容：在所有输出处使用编码修复工具
- 目标：确保中文需求文档能正常显示

### 任务3：修改IDE桥接器
- 修改文件：`skills/ide_bridge/bridge.py`
- 修改内容：确保文件读写使用UTF-8编码
- 目标：防止文件读写时的编码错误

### 任务4：创建测试脚本
- 文件路径：`tests/test_encoding.py`
- 功能：测试编码修复效果
- 包含：
  - 测试中文文件读写
  - 测试控制台输出
  - 测试子进程执行

### 任务5：更新文档
- 文件路径：`docs/encoding_guide.md`
- 内容：Windows环境下的编码处理指南
- 包含常见问题和解决方案

## 技术细节

### 编码处理方案
1. **统一使用UTF-8** - 所有文件读写使用UTF-8编码
2. **控制台输出适配** - 检测系统编码并自动转换
3. **子进程编码指定** - 执行命令时明确指定编码

### 关键代码示例
```python
# 安全的打印函数
def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        # 转换为系统编码
        encoded = text.encode(sys.stdout.encoding, errors='replace')
        print(encoded.decode(sys.stdout.encoding))
```

## 预期结果
1. ✅ 中文需求文档正常显示
2. ✅ 控制台输出无乱码
3. ✅ 文件读写无编码错误
4. ✅ 子进程输出正确捕获
5. ✅ 提供完整的编码处理工具

## 优先级
高 - 影响系统可用性和用户体验

## 测试验证
任务完成后，运行以下测试：
1. `python tests/test_encoding.py` - 编码测试
2. 重新运行完整工作流测试 - 验证修复效果
3. 检查控制台输出 - 确保无乱码

## 备注
此任务将在熄屏状态下执行，测试Antigravity的离线工作能力。