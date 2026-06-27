# ab-review

A/B 双角色多轮审阅-修改工作流。B 审阅挑刺，A 逐条修改，自动迭代直到终审通过。文档和 RTL 代码均适用，自动分流用不同标准。

## 两个模式

| 模式 | 机制 | 适用场景 |
|------|------|----------|
| **默认（单 agent）** | 同一回答内 A/B 交替，最多 3 轮 | 日常审阅，快速闭环 |
| **--split（双终端）** | A/B 分跑两个进程，`/loop` 定时轮询，`.ab-review/state.json` 协调 | 严格隔离、不同模型、长时间运行 |

## 对象分流

按 target 扩展名自动判定 `object_type`，两类对象用不同的审阅标准：

| object_type | 扩展名 | B 审阅标准 | B 专项清单 |
|-------------|--------|-----------|-----------|
| `doc` | `.md` `.txt` | 6 条（数据流/算法/公式） | 5 条（硬件资源/术语/信号追踪/层级/注释） |
| `rtl` | `.v` `.sv` `.vhd` | 6 条（信号/数据通路/FSM/CDC/接口/特殊处理） | 5 条互补式（设计意图/语义，不重复 Mode B） |

RTL 对象自动叠加 rtl-analyze：B 调 Mode B/C 做专项检查，A 调 Mode E 做文档生成/对齐。

## 触发

两种方式等价：

```
# 斜杠命令
/ab-review design-note.md
/ab-review rtl/wifi_phy/top.sv 第3-5节

# 自然语言（含触发词即路由）
AB审阅：对 docs/design-note.md 执行 A/B 多轮审阅，B 终审为止。
```

## 双终端分角色操作（--split）

命令和自然语言均可用，以下按自然语言方式介绍：

**终端 1 — B 审阅者（先启动）**：
> 准备发起 AB 审阅，你是 B，--split --init，审阅目标是 docs/design-note.md

`--init` 告诉 B：建 `.ab-review/state.json`，跑首轮审阅，输出意见后 handoff → 等 A 接手。首轮跑完 state 置 `turn=a`，B 即退出——**不会自动回来**。因此收到 B 的首轮意见后，必须立即在此终端挂轮询让 B 持续待命：

> 开始轮询，每 2 分钟 /loop /ab-review docs/design-note.md --split --role b

**终端 2 — A 修改者（等 B 首轮完成后再启动）**：
> 准备发起 AB 审阅，你是 A，--split，审阅目标是 docs/design-note.md

A 首次运行检查 state 发现 `turn=a` → 读 B 首轮意见 → 逐条决策修改 → handoff 回 B（`turn=b, round=2`）。然后同样挂轮询：

> 开始轮询，每 2 分钟 /loop /ab-review docs/design-note.md --split --role a

之后两端自动乒乓：各自每 2 分钟唤醒，`claim` 探活——该自己动一步，不该自己速退。B 输出 `**终审通过**` 后两端终止。

**要点**：B 终端 `--init` 和 `/loop` 必须紧邻执行；必须先 B 后 A；`state.json` 所有读写走 `_ab_state.py`，禁止 LLM 直接 Edit/Write。

## 核心约束

- **B 不找茬**：已说清楚处不挑，每条意见必须说明理解障碍原因
- **A 不臆造**：改前必须 Grep/Read 核对，无依据不改，无法验证标 `【待验证】`
- **逐条审计**：A 每条决策留依据链（命令+行号），B 下轮可复核，禁止批量接受
- **终审信号**：B 输出 `**终审通过**` → 自动停止；3 轮到顶输出遗留清单
- **防多轮遗忘**：每轮只回顾上一轮，历史落盘按需查；rtl-analyze 报告落盘备查不进对话

## 终止

- **自动终止**：B 输出 `**终审通过**` → 两端下次唤醒见 `verdict=通过` 即停；或 3 轮到顶 → A 置 `verdict=遗留`
- **手动终止**：在挂着 `/loop` 的终端按 `Ctrl+C` 停止轮询；或 `rm .ab-review/state.json` 让两端下次唤醒看到异常退出
- **--split 之外**：`/loop` 7 天自动过期，不需要永久运行

## 文件

| 文件 | 作用 |
|------|------|
| `SKILL.md` | 执行指令（system prompt，每轮加载） |
| `REFERENCE.md` | 参考内容（范文、模板、维护说明，按需 Read） |
| `scripts/_ab_state.py` | `--split` 模式原子状态管理器 |
| `scripts/_ab_split_selftest.py` | state 机端到端自测（25 项断言） |
| `ab_review_onepage.html` | 一页纸可视化说明 |

## 维护

改 `_ab_state.py` 后必跑 `python3 scripts/_ab_split_selftest.py` 回归。改审阅规则（检查清单/模板/格式）后靠人工跑一次默认模式 + split 模式验证。SKILL.md 保持精简（<450 行），纯参考内容放 REFERENCE.md，不在每轮 system prompt 膨胀。