# ab-review REFERENCE（参考内容，按需查阅）

> 本文承接 SKILL.md 的非每轮必用参考内容（端到端示例、--strict 模板、unknown 试探、Bash 序列、维护说明）。
> SKILL.md 每轮加载；本文件只在需要时 Read 对应小节，不占每轮 system prompt。

## §1 端到端示例

### 文档对象示例（object_type=doc）

输入：`/ab-review design-note.md`（小文档，单 agent 双角色）

```
## 第 1 轮 — B 审阅：design-note.md
**本轮范围**: 全文
**意见数**: 2条

### B-1 术语未定义
- **位置**: §2 第 3 段 "CPE 数量为 4"
- **问题**: CPE 首次出现未定义，新读者不知道是"每载波用户设备"还是其他
- **建议**: 首次出现处加一句话定义

### B-2 信号流与代码不符
- **位置**: §3 "rx_data 从 PHY 直接送到 MAC"
- **问题**: Grep 代码发现 rx_data 实际经过 rx_fifo 缓冲（PHY→rx_fifo→MAC），文档遗漏一级
- **建议**: 补充 rx_fifo 一级

---
## 第 1 轮 — A 修改
### A-1 对应 B-1（术语未定义）
- **依据**: `Grep -ri "CPE" rtl/ docs/` → 命中 docs/glossary.md line 12 "CPE: Contention Period Extension"，确认含义
- **判定**: 改
- **理由**: 术语有定义依据，文档首次出现处应补
- **改动**: design-note.md §2 第3段 "CPE 数量为 4" → "CPE（Contention Period Extension）数量为 4"

### A-2 对应 B-2（信号流不符）
- **依据**: `Read rtl/top.sv` line 87-102 → rx_data 经 u_rx_fifo 实例，连线 PHY→rx_fifo→MAC
- **判定**: 改
- **理由**: B 意见有代码支撑，文档遗漏一级
- **改动**: design-note.md §3 "rx_data 从 PHY 直接送到 MAC" → "rx_data 从 PHY 经 rx_fifo 缓冲送到 MAC"

**本轮汇总**: 改 2 | 拒绝 0 | 待验证 0

---
## 第 2 轮 — B 审阅：design-note.md
**本轮范围**: 全文
**意见数**: 0条

**终审通过**

---
## 终审结论
- **对象**: design-note.md
- **执行轮次**: 2 / 3
- **结果**: 终审通过
- **修改统计**: 共修改 2 处，拒绝 0 处
```

### 代码对象示例（object_type=rtl）

输入：`/ab-review rtl/top.sv`（小 RTL，单 agent，object_type=rtl → 代码替代标准 6 条 + B 代码专项 5 条 + rtl-analyze Mode B）

```
## 第 1 轮 — B 审阅：rtl/top.sv（代码对象）
**本轮范围**: 全文
**意见数**: 3条

### B-1 位宽截断无声（互补专项 #1，Mode B 未报）
- **位置**: line 89 `assign trimmed = wide_data[15:0];`
- **问题**: wide_data 32bit 截到 16bit，Mode B 只报位宽匹配（无违规），但截断处无注释说明为何丢弃高 16bit——设计意图缺失
- **建议**: 加注释说明饱和/舍入策略，或命名显式标 `_trunc`

### B-2 FSM 死状态的设计原因（互补专项 #2，追问 Mode B 报的不可达）
- **位置**: line 220-260
- **问题**: Mode B 报 X_STATE 不可达。本条追问：是设计冗余（防御 SEU）还是遗漏？case 未覆盖且 default 依赖未定义条件信号，倾向遗漏
- **建议**: 补 X_STATE 显式处理，或从枚举移除避免综合推断死逻辑

### B-3 复位值不合理（互补专项 #5，追问 Mode B 报的复位缺失之外）
- **位置**: line 45 `counter <= 8'hFF;`
- **问题**: Mode B 报复位存在（无违规），但复位值 0xFF 对计数器不合理——应从 0 起
- **建议**: 复位值改 0，或注释说明为何初值为 0xFF

---
## 第 1 轮 — A 修改
### A-1 对应 B-1
- **依据**: `Read rtl/top.sv` line 89 → wide_data 来自 ADC 12-bit 有效，高 4bit 是符号扩展
- **判定**: 改
- **改动**: line 89 加注释 `// ADC 12-bit effective, [31:16] sign-extend, keep [15:0]`
### A-2 对应 B-2
- **依据**: `Grep "X_STATE" rtl/top.sv` → 仅枚举声明，无 case 分支，确认为遗漏
- **判定**: 改
- **改动**: line 258 补 `X_STATE: next_state = IDLE;`
### A-3 对应 B-3
- **依据**: `Read rtl/top.sv` line 45 → counter 为下行计数，0xFF 是有意预设（启动满量程）
- **判定**: 拒绝
- **理由**: B 未知 counter 用途，复位值 0xFF 是设计意图，补注释而非改值
- **改动**: line 45 加注释 `// active high reset to full-scale (down-counter)`

**本轮汇总**: 改 2 | 拒绝 1 | 待验证 0
```

> 注：上例 B 意见均标注"互补专项 #N，Mode B 未报/追问 Mode B 报的"——体现互补式不重复。

## §2 --strict 模式 Agent prompt 模板

`--strict` 用 `Agent` 工具 spawn 独立 subagent 充当 B（`subagent_type: "general-purpose"`），主 agent 充当 A。B 的上下文与 A 隔离，审阅更严。每轮 B 的意见作为 Agent 返回值交给 A 执行。B 的 prompt 须明确：

> "你是审阅者 B，必须用 `Skill(skill="rtl-analyze", args="评审代码/评审文档 <path>")` 调 rtl-analyze Mode B/C 做专项检查，再叠加本 skill 的 6 默认标准 + 5 硬件专项清单（doc）或 6 代码替代标准 + 5 代码专项（rtl）。"

## §3 unknown 对象试探细节

target 扩展名非 `.md`/`.v`/`.sv`/`.vhd`/`.vhdl` 时，init 前 Read target 前 50 行试探：
- 含 `module`/`entity`/`always_ff`/`always @` → `rtl`
- 含 `##`/`# ` 标题+段落 → `doc`
- 都不像 → 问用户

## §4 --split Bash 典型唤醒序列

`claim` 是只读探活（不加锁写），`handoff`/`finish` 是加锁推进。B 角色每次唤醒：

```bash
CLAIM=$(python3 ~/.claude/skills/ab-review/scripts/_ab_state.py claim b)
ACT=$(echo "$CLAIM" | python3 -c "import sys,json; print(json.load(sys.stdin).get('act'))")
if [ "$ACT" = "True" ]; then
    # Read target + a-round-{round-1}.md，执行 B 审阅，Write b-round-{round}.md
    # 若无实质意见 → finish 通过；否则 handoff b
else
    echo "等待中或已终止：$CLAIM"
fi
```

## §5 维护说明

### 脚本清单

| 脚本 | 作用 | 何时改 |
|------|------|--------|
| `scripts/_ab_state.py` | `--split` 模式的 state 原子管理器（init/claim/handoff/finish/reset/set-type）——state.json 唯一写入者 | 改 state schema、流转规则、锁机制时 |
| `scripts/_ab_split_selftest.py` | `_ab_state.py` 的端到端自测 | 每次 `_ab_state.py` 改动后回归 |

### 回归自测（改 `_ab_state.py` 后必跑）

```bash
python3 ~/.claude/skills/ab-review/scripts/_ab_split_selftest.py
```

在临时目录跑，自动清理。覆盖：正常流转 `b→a→b→done`、互斥锁、max_rounds 耗尽、init 幂等、done 后 handoff no-op、object_type 持久化、set-type 纠正。

**全过输出** `ALL PASS — state machine verified: ...`；任一断言失败打印 `FAIL <断言>` 并 exit 1。改了 state 流转逻辑后此脚本不过，禁止上线。

### 脚本调用约定

`--split` 运行时所有 state 读写走 `_ab_state.py`，**禁止** LLM 直接 Edit/Write `.ab-review/state.json`（绕过 flock+os.replace 破坏原子性）。新增 state 字段时同步更新 `_ab_split_selftest.py` 断言。

### 改 skill 正文的回归

改了检查清单 / 轮次格式 / A 决策模板 / 终审信号等**审阅规则**（非 state 机）后，自测脚本不覆盖（它只测 state 机）。这类改动靠实际跑一次 `--split` 或默认模式人工验证格式一致性。