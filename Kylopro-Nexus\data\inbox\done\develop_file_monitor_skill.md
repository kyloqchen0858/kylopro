# 开发任务：实现文件监控技能

## 需求描述
实现Kylopro-Nexus Phase 2中的文件监控技能，用于监控指定目录的文件变化，并调用Ollama进行本地摘要。

## 具体任务
1. 在skills目录下创建file_monitor文件夹
2. 创建file_monitor技能的核心Python模块（monitor.py），包含文件系统监控和事件处理
3. 创建SKILL.md文件，描述技能的使用方法
4. 集成Ollama本地模型进行文件内容摘要
5. 编写测试脚本验证功能

## 预期结果
- file_monitor技能可以监控目录变化
- 能够对新增或修改的文件调用Ollama进行摘要
- 技能可以通过nanobot正常加载和使用
- 提供完整的测试用例

## 优先级
高 - Phase 2核心功能