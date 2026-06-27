---
name: rtl-analyze
description: "写RTL / 分析代码 / 评审代码 / 评审文档 / 优化代码 / 检查文档 / 写模块 / 新建模块 / 添加功能 / 重构 / 设计模块"
user-invocable: true
argument-hint: "[文档或RTL路径] [可选: 分析模式/范围]"
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Skill, Agent
metadata:
  type: analysis
  domain: rtl
---

# rtl-analyze（占位）

> ⚠️ 此 skill 为占位骨架，真实分析逻辑待后续补充。

当前调用 `/rtl-analyze <target>` 时，Claude 会基于此 SKILL.md 加载上下文，
但不会执行实质性的 RTL 专项分析。计划补充的能力：

- **Mode A — 分析代码**：模块结构、信号追踪、层次关系
- **Mode B — 评审代码**：编码风格、综合就绪、FSM/CDC/PPA 检查
- **Mode C — 评审文档**：文档 ↔ RTL 交叉核对
- **Mode E — 文档生成**：从 RTL 逆向生成/对齐/增量更新文档

如需临时分析，可直接让 Claude 读 RTL 文件做通用审查。
