# rtl-analyze

ASIC / FPGA RTL 分析、评审、文档核对、代码生成、文档逆向 的五模式 skill。领域无关内核 + 可插拔领域扩展。

## 五个模式

| Mode | 触发词 | 用途 |
|------|--------|------|
| **A** 分析代码 | 分析代码 / analyze module | 单模块深度分析：端口/参数/时钟域/FSM/数据通路/PPA，输出分析报告 + Mermaid 图 |
| **B** 评审代码 | 评审代码 / code review | 代码质量审计：编码风格/latch/FSM/CDC/综合/结构/PPA/DFT/领域专项（9 大类），输出 severity 分级清单 |
| **C** 评审文档 | 评审文档 / cross-check doc | 文档 ↔ RTL 交叉核对：信号名/位宽/参数/层次/时钟域是否与代码一致 |
| **D** 写代码 | 写代码 / write RTL / 重构 | 生成/修改/优化/重构 RTL，先搜项目同类模块复用风格再产出 |
| **E** RTL→文档 | 逆向文档 / 文档对齐 / 增量更新文档 | 从 RTL 生成设计文档：E-1 逆向 / E-2 漂移对齐 / E-3 增量更新 |

## 触发

由 description 触发词自动路由，也可由其他 skill（如 ab-review）通过 `Skill()` 调用：

```
Skill(skill="rtl-analyze", args="分析代码 rtl/xxx.sv")
Skill(skill="rtl-analyze", args="评审代码 rtl/xxx.sv")      # Mode B
Skill(skill="rtl-analyze", args="评审文档 docs/xxx.md")     # Mode C
Skill(skill="rtl-analyze", args="逆向文档 rtl/xxx.sv")      # Mode E-1
```

> 由 `Skill()` 调用时 args 必须含模式关键词；歧义则默认 Mode A 执行并标注，不反问（保护调用方自动流程）。

## 项目上下文加载

每次执行前按优先级获取约定：
1. 项目 `CLAUDE.md` / `MEMORY.md` / `memory/` → 复位电平、命名、宏前缀、目标工艺/器件/频率
2. 领域关键词命中 → 叠加对应领域扩展检查
3. 无约定 → 用 skill 末尾"通用约定默认值"回退

## 领域扩展（可插拔）

主框架 ASIC/FPGA 通用，领域专项按项目关键词叠加：WiFi/802.11、视频编解码（H.264/H.265）、网络/通信（以太网/SerDes）、SoC/总线（AXI/AHB/APB）、AI/NPU 计算。多领域命中全部叠加、独立汇报。按 skill 内"如何新增一个领域"模板可增补其他领域。

## 关键约束

- **Mode E 事实优先**：只描述代码已实现的事实，设计意图标 `【待确认】` 交还设计者，不编造。
- **Mode D 先搜后写**：写代码前必须 Grep 项目同类模块，搜到复用、搜不到才用通用默认。
- **PPA 必先确认工艺/器件**：未指定则绝对数值标 `@unspecified process`，只给相对评估。
- **输出语言**：用户交互跟随 prompt；`Skill()` 调用跟随调用方（ab-review 默认中文）。

## 文件

- `SKILL.md` — 五模式规范 + 领域扩展 + 通用约定默认值 + 维护说明
- 无脚本依赖（纯规范型 skill）

## 维护

改检查清单/格式后按 `SKILL.md` 末尾"维护说明"的 5 步人工回归流程验证。改动原则：Mode 结构稳定勿改，领域扩展可自由增补，主框架不得再引入领域硬编码。