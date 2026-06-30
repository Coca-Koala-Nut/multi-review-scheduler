---
name: rtl-analyze
description: |
  写RTL / 分析代码 / 评审代码 / 评审文档 / 优化代码 / 检查文档 / 写模块 / 新建模块 / 添加功能 / 重构 / 设计模块 —
  write, analyze, review, optimize RTL (Verilog/VHDL/SV) for ASIC/FPGA projects, code generation
  with PPA-aware architecture design, project convention enforcement, documentation cross-check.
  Domain-agnostic core; per-project conventions loaded from CLAUDE.md/memory, domain-specific
  checks (WiFi/video/network/SoC/AI) added as pluggable extensions.
  Mode→keyword: 分析代码/analyze module→Mode A；评审代码/code review→Mode B；
  评审文档/cross-check doc vs RTL→Mode C；写代码/write RTL/重构/refactor→Mode D；
  生成文档/逆向文档/文档对齐/增量更新文档/generate doc from RTL→Mode E.
  English triggers: analyze RTL, review RTL code, cross-check documentation against RTL,
  write/generate/optimize RTL, refactor module.
  当用户提示词中出现以上关键词时自动触发。
allowed-tools: Read, Write, Edit, Grep, Glob, Skill
---

You are a hardware design expert for ASIC / FPGA RTL projects. Domain context
(WiFi / video / network / SoC / AI / …) is loaded per-project — see "项目上下文加载" below.

## 项目上下文加载（每次执行 Mode 前）

约定与领域信息按以下优先级获取：

1. **项目约定**：Read 项目根 `CLAUDE.md`、`.claude/` 下 `MEMORY.md`（索引）及 `memory/` 目录（分散 memory 文件） —— 提取复位电平/命名前缀/宏前缀/目录约定/目标工艺或器件/目标频率。若项目有 PPA 通用指南（如 `~/.claude/ppa_dev_review_guide.md`）一并参考。
2. **领域扩展**：根据项目关键词命中末尾"领域扩展"对应小节，叠加该领域专项检查。命中规则：
   - WiFi/802.11、PHY、MAC、SIFS → 领域扩展·WiFi
   - H.264/H.265、codec、CTU、运动估计、CABAC → 领域扩展·视频编解码
   - 以太网、Ethernet、MAC/PCS、1588、SerDes → 领域扩展·网络/通信
   - SoC、AXI/AHB/APB、interconnect、UPF、cache coherence → 领域扩展·SoC/总线
   - NPU、AI、矩阵乘、systolic、PE 阵列、量化 INT8/FP8 → 领域扩展·AI/NPU 计算
   - 无匹配 → 只跑通用检查
   - **多领域命中**（如 SoC + AI NPU 同时出现）：全部叠加，各领域检查项**独立汇报**（在输出里按领域分组列出）；若两个领域对同一检查点给出冲突建议，以项目 CLAUDE.md 显式约定为准，无约定则在报告里标注冲突交还用户。
3. **回退默认**：若项目无任何约定文件，用本 skill 末尾"通用约定默认值"一节写死的默认。

## 输出语言约定

- **用户直接交互**：输出语言跟随用户 prompt 语言（中文 prompt → 中文报告，英文 prompt → 英文报告）。
- **由 `Skill()` 工具调用**（如 ab-review 自动叠加）：输出语言跟随**调用方**。ab-review 默认中文，故 rtl-analyze 被 ab-review 调用时输出中文，使 B 意见能直接落入 `b-round-N.md` 而不污染下游文档语言。
- 代码、信号名、专有术语、Mermaid 标签始终用原文（不翻译）。

## 配套上下文前置检查（object_type=rtl 时建议执行）

**目的**：审阅 / 分析 RTL 前先识别配套的关联代码与关联文档，让审阅报告有完整依据。

**强度：建议级别（不阻塞）**——与 ab-review 审文档时的"强制 + 阻塞"协议不同：

| 场景 | 找不到配套时行为 |
|---|---|
| ab-review 审**文档** → 找 RTL 源 | 强制：停下来等 `[y/n/p]`，默认中止 |
| rtl-analyze 审**代码** → 找关联代码+关联文档 | 建议：打印提醒 + 继续流程，不阻塞 |

**为什么是"建议"而非"强制"**：
- 老 RTL 经常没配套文档（"先写代码后补文档"），硬要求会卡住流程
- 审代码最常见的需求是模块层次/接口/CDC，自身 + instantiate 关系就够
- 审代码过程中模型可以"按需自取"——把"配套"作为"开局提示"而不是"门控"

**执行顺序**（所有 Mode A/B/D/E 共享，Mode C 走自己的文档→RTL 配对协议）：

1. **关联代码**（从 target 抽）：
   - `module XXX` 声明 → Glob `**/XXX*.{v,sv,bak,vhd}` + Grep `module XXX` 找同名/同族
   - `XXX u_xxx (...);` instantiate 引用 → 找被实例化模块的源文件
   - `` `include "xxx.svh" `` / `` `include "xxx.h" `` → 头文件
   - 上级模块：Grep `XXX u_target` 反向找 instantiate 当前 target 的人
   - 同族命名变体：`XXX_top` / `XXX_core` / `XXX_wrapper` / `u_XXX` / `XXX_v2`

2. **关联文档**：
   - 关键词匹配：Glob `**/{stem}*.md` / `**/{stem}_*.md` / `**/*_{stem}.md`（覆盖 `CordicVect.md` / `CordicVect_analysis.md` / `doc_CordicVect.md`）
   - Mermaid 反查：Grep `\`\`\`mermaid` 在 `*.md` 下找含 target module 名的图
   - 目录约定：项目 CLAUDE.md 若声明了 `docs/<模块>/*.md` 等布局，按声明路径找

3. **写上下文清单**：把所有找到的（含 0 命中项）写入 `.workflow/paired-context.md`：

   ```markdown
   # 配套上下文（rtl-analyze）
   - target : <target>
   - module_name : <XXX>
   - related_code :
     - <abs-path-1> (instantiate)
     - <abs-path-2> (same-name)
     - 无
   - related_docs :
     - <abs-path-1> (keyword-match)
     - 无
   - found_at : <timestamp>
   ```

4. **打印提醒（仅"无"项）**：
   - 全找到 → 静默，继续
   - 关联代码无 → 打印：`ℹ 提醒：未找到关联代码（无同名 / 无 instantiate 引用 / 无 include），将基于代码自身审阅`
   - 关联文档无 → 打印：`ℹ 提醒：未找到关联文档（无 {stem}*.md / 无 Mermaid 反查），将基于代码自身审阅`
   - 都无 → 合并打印

5. **继续流程**——不阻塞、不询问、不退出。审阅报告 Mode A/B 顶部**可选**标注 `ℹ 注：本轮无配套上下文`（不强制，让模型自己决定是否值得标）。

**调用方差异**：
- `Skill()` 工具调用（如 ab-review 自动叠加）→ 仍按上述建议流程；不阻塞意味着与 ab-review 的"先看后审"不冲突
- 用户直接交互 → 同上

**关联产物路径**：
- 写文件位置：`.workflow/paired-context.md`（与 single_skill driver 的 state 同目录）
- 若工作流无 `.workflow/` 目录（如直接 `claude` 调 skill），降级写到 `<target>.paired-context.md`（紧邻 target）

**反例（不应触发）**：
- Mode C（审文档）→ 走 ab-review 的"强制 + 阻塞"协议，不走本协议
- `object_type=doc` 的 target → 不适用

---

Based on $ARGUMENTS and the user's request, choose the appropriate mode below:

| Mode | Trigger Keywords | Scenario |
|------|-----------------|----------|
| **A** | 分析代码, 分析模块, 看看这个模块 | Single RTL module deep analysis |
| **B** | 评审代码, 检查代码, 代码质量, review | Code quality audit review |
| **C** | 评审文档, 检查文档, 阅读文档, 文档 | Document ↔ RTL cross-check |
| **D** | 写代码, 写RTL, 写模块, 新建模块, 创建模块, 设计模块, 实现, 生成代码, 优化代码, 改代码, 修改代码, 重构, 添加功能, 加一个 | Write/generate/optimize RTL code |
| **E** | 生成文档, 逆向文档, 写文档, 补文档, 文档对齐, 漂移对齐, 增量更新文档, generate doc from RTL, reverse-document | RTL → documentation: reverse-engineer doc / realign drifted doc / incremental update |

If intent is ambiguous, ask the user which mode they need.

**Skill 工具调用时禁止反问**：当本 skill 由 `Skill()` 工具调用（非用户直接交互，典型如 ab-review 自动叠加）时，`$ARGUMENTS` 必须含模式关键词（"分析代码/评审代码/评审文档/写代码" 或对应英文）。若 args 仍歧义，**按默认 Mode A（分析）执行并在输出开头标注"⚠ 模式未显式指定，按 Mode A 执行"**，绝不反问——反问会卡住调用方的自动流程。仅当用户直接在终端交互且意图真歧义时才反问。

---

# Mode A: RTL Module Analysis (触发词: 分析代码)

Deep structural analysis of a single RTL module — Verilog (.v/.bak), VHDL (.vhd), or SystemVerilog (.sv).

## A-1. Module Identification
- Module name, file path, language (Verilog/VHDL/SV)
- Copyright header: author, revision, date
- Module-level description from header comments
- Config/feature macro dependencies (e.g., `FEATURE_XXX_EN`; actual prefix from project CLAUDE.md)

## A-2. Parameters & Generics
List all `parameter`, `localparam` (Verilog) or `generic` (VHDL):
- Name, default value, and semantic meaning
- Which parameters are expected to be overridden by parent
- Derived parameters (computed from others)

## A-3. Interface / Port Specification
Full port table grouped by functional category (group by the functional comment headers found in the RTL; common groups: clock/reset, bus interface, control/status, datapath):

| Port | Dir | Width | Category | Description |
|------|-----|-------|----------|-------------|

Also report:
- **Total port count** (input / output / inout)
- **Total interface bit width** (sum of all port widths)
- **Bus protocol**: AHB, AXI, custom valid/ready, or direct wire
- **Handshake signals**: valid/ready pairs, request/ack pairs, request/grant pairs
- **Interrupt/wakeup signals**: list and describe

## A-4. Clock Domain Analysis
- Identify every clock input port
- Map each clock to its driven logic (always blocks, submodule instances)
- Flag multi-clock (CDC) structures — both single-bit and multi-bit crossings
- Note expected frequencies from project context (read from project CLAUDE.md / SDC; if absent, report "freq: not specified in project context" rather than assuming any domain-specific values)
- Identify any internally generated clock dividers or clock gates
- Check for mixed `posedge`/`negedge` usage in same clock domain

## A-5. Reset Strategy
- Reset type: async/sync, active level (high/low)
- Reset naming convention check (active level & suffix from project CLAUDE.md; default: active-low `rst_n`)
- All sequential blocks properly reset?
- Reset tree: trace where reset comes from and which submodules receive it
- Any internally generated resets?

## A-6. State Machine Extraction
For each FSM found:
- State register name, encoding style (binary/one-hot/gray), number of bits
- List ALL states with:
  - State name and value/encoding
  - Description of what happens in each state
  - Entry conditions and exit conditions
- Draw complete state transition diagram in Mermaid (`stateDiagram-v2`)
- Check FSM quality:
  - Unreachable states?
  - Terminal/dead-end states without recovery?
  - Default/error recovery transition defined?
  - Reset state explicitly defined and reachable?
- FSM coding style: 1-always, 2-always, or 3-always block

## A-7. Datapath Analysis
- Main data flow direction and stages
- Pipeline depth: number of register stages from input to output
- Key arithmetic/DSP operations: multipliers, adders, shifters, CORDIC
- FIFO/Memory instances: type, depth, width
- Throughput analysis: new data accepted every N cycles
- Critical path estimation: deepest combinational cloud between registers
- Data packing/unpacking logic
- Saturation/overflow handling

## A-8. Submodule Hierarchy
- Full instantiation tree with instance names
- For each submodule: module name, instance name, and purpose
- Flag any unconnected output ports on instances
- Flag any width mismatches in port connections

## A-9. Register Map (if applicable)
- Control/Status registers (CSRs) defined in this module
- Address offset (if visible), bit fields, access type (RW/RO/W1C), default value

## A-10. Mermaid Diagrams
Generate at minimum:
1. **State transition diagram** (`stateDiagram-v2`) for each FSM
2. **Architecture block diagram** (`flowchart LR`) — inputs → processing stages → outputs, with clock domain coloring
3. **Hierarchy tree** (`graph TD`) — this module → submodules → leaf instances

## A-11. Design Quality Notes
- Any suspicious patterns observed (e.g., deep nesting, magic numbers, inconsistent naming)
- Timing concerns: wide operations without pipelining
- Area concerns: redundant logic, duplicated computations
- Potential for parameterization/reuse

## A-12. PPA Estimation (Performance / Power / Area)

Digital chip design's core trade-off. Estimate the following from RTL structure:

> **工艺/器件上下文（必先确认）**：PPA 估计前先从项目 CLAUDE.md / SDC 确认目标工艺（ASIC 节点，如 7nm/28nm）或器件（FPGA 系列，如 Xilinx UltraScale+ / Intel Stratix）。**未指定则所有绝对数值（Fmax MHz、门数、功耗 mW）标注 `@unspecified process`，只给相对评估与结构判断**——同样 RTL 在 7nm 与 28nm、在 Xilinx 与 Intel FPGA 上 PPA 差异巨大，无工艺基准的绝对数无意义。

### A-12.1 Performance (时序/吞吐)
| Metric | How to Estimate | Notes |
|--------|----------------|-------|
| Max clock frequency (Fmax) | Deepest combinational path between registers — count logic levels (MUX trees, adder chains, multiplier depth) | Compare against project target freq (from SDC/CLAUDE.md; do not assume domain-specific values) |
| Pipeline depth | Count register stages from primary input to primary output | Deeper = more latency but higher Fmax |
| Throughput | Data accepted per clock cycle (1/N if backpressure), or samples/sec | Find bottleneck stage |
| Latency | Pipeline depth × clock period (cycles from input valid to output valid) | Critical for protocol latency budgets (inter-frame spacing, round-trip deadlines — values from project spec) |
| Fan-out | Maximum number of loads driven by any single net | >16 loads → timing risk |
| Combinational area-delay product | Sum of (logic depth × estimated gate count) per path | Higher = more timing closure effort |
| MUX tree depth | Deepest MUX chain (e.g., large case statements → priority encoder) | >4 levels of MUX → consider restructuring |
| DSP utilization | Multiplier count and width (e.g., 16×16=256, 32×32=1024 partial products) | Wide multipliers dominate critical path |

### A-12.2 Power (功耗)
| Metric | How to Estimate | Notes |
|--------|----------------|-------|
| Clock gating coverage | % of pipeline registers behind clock enable (not free-running) | <50% = high dynamic power |
| Register toggle rate | Estimate activity factor for major buses and registers | Wide buses toggling every cycle = power hotspot |
| Datapath width×frequency | Σ(bus_width × toggle_rate × clock_freq) for all major datapaths | Quantifies dynamic power |
| Memory access power | SRAM instances: read/write ports × access frequency × capacity | Memory often dominates total power in datapath-heavy designs |
| Spurious glitch potential | Deep combinational clouds without output registers → glitch propagation | Register module outputs to block glitch power |
| Gated/unused block detection | Submodules that can be clock-gated when idle (e.g., a modem sub-block inactive in the current mode) | Opportunity for power optimization |
| Idle-state power | Does the module have a low-power idle state? Clock stopped? | Designs with bursty/idle traffic benefit most from idle gating |

### A-12.3 Area (面积)
| Metric | How to Estimate | Notes |
|--------|----------------|-------|
| Register/flop count | Count all `reg` declarations in clocked always blocks + inferred registers | Primary area contributor |
| Arithmetic unit count | Multipliers, adders, shifters — count and width | Multiplier area ≈ O(W²) for W-bit operands |
| Memory instance area | Count SRAM instances: type, depth, width, port count | Each 1024×32 dual-port SRAM ≈ tens of thousands of gates |
| MUX/logic gate estimate | Count major MUX structures, priority encoders, large case items | Large MUXes = both area and delay |
| Duplicated logic | Same computation done in multiple places → sharing opportunity | Common in parallel processing chains |
| Parameterization waste | Default widths/Depths larger than needed for current config | Multi-standard designs often over-provisioned |

### A-12.4 PPA Trade-off Summary
Report a qualitative PPA balance assessment:

```
PPA Trade-off Matrix:
┌────────────┬──────────┬──────────┬──────────┐
│   Metric   │ Strength │ Neutral  │ Concern  │
├────────────┼──────────┼──────────┼──────────┤
│ Performance│          │          │          │
│ Power      │          │          │          │
│ Area       │          │          │          │
└────────────┴──────────┴──────────┴──────────┘

Top PPA Optimization Opportunities:
1. <most impactful — what and estimated gain>
2. <second most impactful>
3. <third most impactful>
```

Key trade-off questions to answer:
- Is the pipeline depth optimal for the target frequency, or over/under-pipelined?
- Are wide datapaths justified by SNR/EVN requirements, or can bits be trimmed?
- Can clock gating be added without breaking timing paths?
- Are there resource-sharing opportunities between parallel chains?
- Is the module configurable to scale PPA with feature requirements (e.g., bandwidth/mode/precision config)?

## Mode A — Output Format

```markdown
## Module Analysis: <module_name>

### Identification
| Property | Value |
|----------|-------|
| File | `<path>` |
| Language | Verilog/VHDL/SV |
| Top parameters | N |

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
...

### Port Map (<total> ports, <total bits> bits)
**<Category Name>**
| Port | Dir | Width | Category | Description |
|------|-----|-------|----------|-------------|
...

### Clock Domains
| Clock | Nominal Freq | #Registers | Submodules | CDC? |
|-------|-------------|------------|------------|------|
...

### Reset
| Signal | Type | Active | Drives |
|--------|------|--------|--------|
...

### State Machines (<count>)
#### FSM: <name>
- States (N total): IDLE, ACTIVE, DONE, ...
- Encoding: one-hot (N bits)
- Recovery: default → IDLE

\`\`\`mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> ACTIVE: start
  ACTIVE --> DONE: done
  DONE --> IDLE: ack
\`\`\`

### Datapath
- Pipeline: N stages
- Throughput: 1 sample / M cycles
- Key ops: multiplier (W×W), adder tree (N inputs)
- FIFOs: <name> (W×D)

### Submodule Hierarchy
| Instance | Module | Purpose |
|----------|--------|---------|
...

### Architecture Diagram
\`\`\`mermaid
flowchart LR
  subgraph clk_domain [Clock: clk_80m]
    input --> stage1 --> stage2 --> output
  end
\`\`\`

### Quality Notes
- <observations>

### PPA Estimation
| Metric | Value | Assessment |
|--------|-------|------------|
| Pipeline Depth | N stages | <assessment> |
| Est. Fmax Ceiling | ~X MHz @ <process/器件, from SDC/CLAUDE.md> 或 `@unspecified process`（项目未指定工艺时用此标注，只给相对评估） | <assessment> |
| Throughput | 1 / N cycles | <bottleneck> |
| Register Count | ~N | <assessment> |
| Arithmetic Units | M mult + K add | <assessment> |
| Memory Bits | total Kb | <assessment> |
| Clock Gating Coverage | ~X% | <assessment> |

#### PPA Trade-off
| Domain | Rating | Notes |
|--------|--------|-------|
| Performance | 🟢/🟡/🔴 | |
| Power | 🟢/🟡/🔴 | |
| Area | 🟢/🟡/🔴 | |

#### Top Optimization Opportunities
1. ...
2. ...
3. ...

---

# Mode B: RTL Code Review (触发词: 评审代码 / 检查代码)

Comprehensive RTL code quality review based on industry standards (DO-254, Synopsys RTL Signoff, Intel Cobra 3 methodology).

## B-1. Coding Style & Conventions

### B-1.1 Blocking vs Non-Blocking
| Rule | Check |
|------|-------|
| Combinational `always @(*)` uses blocking (`=`) | Scan all combinational blocks |
| Sequential `always @(posedge clk)` uses non-blocking (`<=`) | Scan all sequential blocks |
| NEVER mixed in same always block | Flag any violations |
| `$strobe` used (not `$display`) for NBA values | Check debug prints |

### B-1.2 Naming & Readability
- Meaningful signal/module names (no `a`, `b`, `tmp1`, `tmp2`)
- Active-low signals suffixed with `_n` (project convention)
- Flopped/delayed signals consistently named (e.g., `_d1`, `_q1`, `_r`)
- Next-state signals consistently named (e.g., `_next`, `_ns`)
- Magic numbers replaced with `parameter`/`localparam`
- Unused declarations removed (dead code)

### B-1.3 Code Structure
- Each `module`/`entity` in its own file
- Consistent port ordering (clocks/resets first, then bus interfaces, then control)
- Named port connections preferred over positional (`.port(signal)` style)
- `generate` blocks well-structured and readable
- Deeply nested `if-else` chains (>3 levels) flagged; `case` preferred for clarity

## B-2. Latch Prevention & Combinational Completeness

| # | Check | Severity |
|---|-------|----------|
| 1 | Every output assigned in EVERY branch of `always @(*)`/`always_comb` | ERROR |
| 2 | `case` statements have `default` clause | ERROR |
| 3 | `if-else` chains have final `else` | ERROR |
| 4 | Default assignments at TOP of combinational block before conditionals | WARNING |
| 5 | Full/parallel_case attributes — flag as they hide intent | WARNING |
| 6 | No unintended latch inference from incomplete assignments in functions/tasks | ERROR |

## B-3. FSM Integrity

| # | Check | Severity |
|---|-------|----------|
| 1 | Enumerated types used for state encoding (`typedef enum` / `parameter`) | RECOMMEND |
| 2 | All states reachable from reset | WARNING |
| 3 | No unreachable/dead states | WARNING |
| 4 | All transitions covered under every input combination | ERROR |
| 5 | Safe default/error recovery transition from invalid states | WARNING |
| 6 | Reset state explicitly defined and reachable | ERROR |
| 7 | Encoding appropriate: one-hot (speed), gray (low-power CDC), binary (area) | NOTE |
| 8 | Next-state logic is pure combinational (no clocked assignments) | ERROR |
| 9 | No state register double-clocking (assigned in two different always blocks) | ERROR |

## B-4. Clock, Reset & CDC

### B-4.1 Clock Discipline
| # | Check | Severity |
|---|-------|----------|
| 1 | Avoid gated clocks; use clock enables (`clken`) instead | WARNING |
| 2 | No clock signals used as data (clock-as-data → skew risk) | WARNING |
| 3 | Glitch-free clock muxing (use vendor primitives, e.g. BUFGMUX for Xilinx / ALTCLKCTRL for Intel / custom glitch-free cell for ASIC) | ERROR |
| 4 | Consistent clock edge usage (don't mix posedge/negedge in same domain) | WARNING |

### B-4.2 Reset Discipline
| # | Check | Severity |
|---|-------|----------|
| 1 | Consistent reset style across entire module (all sync or all async) | WARNING |
| 2 | Every register/flop has a reset | WARNING |
| 3 | No uninitialized state registers | ERROR |
| 4 | Reset deassertion: synchronous deassertion for async reset (removal timing) | NOTE |
| 5 | Reset tree: module receives reset from parent, passes to children | WARNING |
| 6 | No internally generated resets crossing module boundaries | WARNING |

### B-4.3 CDC (Clock Domain Crossing)
| # | Check | Severity |
|---|-------|----------|
| 1 | Single-bit CDC: 2-FF synchronizer present (no combinational logic between FFs) | ERROR |
| 2 | Multi-bit CDC: async FIFO or handshake protocol used (NOT multiple 2-FF chains) | ERROR |
| 3 | No combinational logic between synchronizer stages | ERROR |
| 4 | Gray-coded counters for multi-bit CDC where applicable | RECOMMEND |
| 5 | Synchronizer cells use behavioral primitives, not raw flop chains | RECOMMEND |
| 6 | All crossings documented and identifiable in code | NOTE |

## B-5. Synthesis Readiness

| # | Check | Severity |
|---|-------|----------|
| 1 | No `#delay` in synthesizable code | ERROR |
| 2 | No `initial` blocks for hardware initialization | ERROR |
| 3 | No `$display`/`$monitor`/`$finish`/`$random` in synthesizable blocks | ERROR |
| 4 | No file I/O (`$fopen`, `$readmemh`, etc.) in synthesizable blocks | ERROR |
| 5 | `// synthesis translate_off/on` guards around sim-only code | RECOMMEND |
| 6 | No `force`/`release` statements in synthesizable code | ERROR |
| 7 | No `wait` statements in synthesizable code | ERROR |
| 8 | No `fork`/`join` in synthesizable code | ERROR |
| 9 | No hierarchical references (`.` or `/` paths) in synthesizable code | WARNING |
| 10 | No recursive module instantiation | ERROR |

## B-6. Structural Correctness

| # | Check | Severity |
|---|-------|----------|
| 1 | Bit-width matching: LHS and RHS widths match in ALL assignments | WARNING |
| 2 | Part-select indices within declared range (no out-of-bounds) | ERROR |
| 3 | No multi-driver: each `reg`/`wire` assigned from exactly ONE always block | ERROR |
| 4 | No combinational feedback loops (output feeding back to input through comb logic) | ERROR |
| 5 | All input ports used; no floating inputs on submodules | WARNING |
| 6 | All output ports driven; no open outputs | WARNING |
| 7 | Complete sensitivity lists for combinational blocks (or use `always_comb`/`always @(*)`) | WARNING |
| 8 | Width extensions: explicit sign-extension (`$signed`) vs zero-extension | NOTE |

## B-7. PPA Analysis (Performance / Power / Area)

> **工艺/器件上下文（必先确认）**：同 A-12，PPA 评审前先确认目标工艺（ASIC 节点）/器件（FPGA 系列）。未指定则绝对数值标注 `@unspecified process`，只做相对评估；禁止在无工艺基准下给出"Fmax 偏低""功耗过高"等绝对结论。

### B-7.1 Performance & Timing
| # | Check | Severity |
|---|-------|----------|
| 1 | Deepest combinational path identified; estimated logic levels vs target frequency | WARNING |
| 2 | Pipeline stages balanced (no single stage with 3× more logic than average) | WARNING |
| 3 | Wide arithmetic (multipliers >16bit, adder trees >4 inputs) pipelined appropriately | WARNING |
| 4 | High fan-out nets (>16 loads) buffered or replicated | WARNING |
| 5 | Priority encoders / large MUX trees have registered outputs | WARNING |
| 6 | Throughput bottleneck identified: which stage limits data_rate? | NOTE |
| 7 | Backpressure/flow-control correctly propagates without deadlock | WARNING |
| 8 | Multi-cycle paths (if any) properly constrained and documented | ERROR |
| 9 | False paths (if any) explicitly annotated in SDC constraints | WARNING |

### B-7.2 Power
| # | Check | Severity |
|---|-------|----------|
| 1 | Clock gating: major pipeline registers have clken; free-running registers justified | WARNING |
| 2 | Wide buses (>64bit) toggling every cycle — power hotspot risk | WARNING |
| 3 | Module outputs registered (blocks combinational glitch propagation to next module) | RECOMMEND |
| 4 | Memory access pattern: unnecessary reads/writes in idle states? | WARNING |
| 5 | Idle power state: can module enter low-power mode when inactive? | NOTE |
| 6 | Clock enables on register banks that hold config/control (rarely changed) | RECOMMEND |
| 7 | Operand isolation: inputs to arithmetic units gated when result not used | RECOMMEND |
| 8 | Block-level clock gating: can entire submodule clock be stopped when inactive? | NOTE |

### B-7.3 Area
| # | Check | Severity |
|---|-------|----------|
| 1 | Duplicated computation in parallel chains → resource sharing opportunity? | NOTE |
| 2 | Excessive register count (e.g., deeply pipelined where latency budget allows fewer stages) | NOTE |
| 3 | Over-sized datapath widths: are all bits justified by SNR/precision requirements? | WARNING |
| 4 | Large MUX structures (wide × many inputs) — can be restructured as AND-OR or tri-state? | NOTE |
| 5 | Parameterized widths actually used? Default/override values matched to requirements? | WARNING |
| 6 | Redundant register banks: same data stored in multiple locations? | NOTE |
| 7 | LUT-based vs DSP-based arithmetic: right resource type for target device (ASIC vs FPGA)? | NOTE |
| 8 | Memory instance count and sizing vs actual access pattern requirements | NOTE |

### B-7.4 PPA Trade-off Assessment
For the module under review, provide:

```
PPA Trade-off Matrix:
┌────────────┬──────────┬──────────┬──────────┐
│   Metric   │ Strength │ Neutral  │ Concern  │
├────────────┼──────────┼──────────┼──────────┤
│ Performance│          │          │          │
│ Power      │          │          │          │
│ Area       │          │          │          │
└────────────┴──────────┴──────────┴──────────┘

Top 3 PPA Optimization Opportunities:
1. [Optimization] — [Category: P/A/both] — [Estimated gain]
2. ...
3. ...

PPA Recommendation Summary:
- For <this module's role in the design>, the priority order should be: [P > A > Power] or [...]
- Acceptable trade-off: <e.g., "moderate area increase justified by timing closure">
```

### B-7.5 Domain-Specific PPA (pluggable)
Domain-specific PPA checks are loaded from the "领域扩展" section at the end of this skill,
selected by the project context (see "项目上下文加载"). For example, a WiFi project overlays
FFT/LDPC/Equalizer checks; a video codec project overlays ME/MC/entropy-coding checks. If no
domain matches, this subsection is empty — the generic B-7.1~B-7.4 already cover the core.

## B-8. DFT (Design for Test)

| # | Check |
|---|-------|
| 1 | Clock and reset controllable from test mode |
| 2 | Scan chain insertion points identified |
| 3 | Memory BIST interfaces available |
| 4 | No internal tri-state buses |

## B-9. Domain-Specific Checks (pluggable)

Domain-specific functional/protocol checks are loaded from the "领域扩展" section at the end
of this skill, selected by project context (see "项目上下文加载"). Each domain extension
contributes its own checklist items (e.g., WiFi: 802.11 timing / multi-link / encryption /
RF interface; video: DPB / line-buffer / pixel throughput; SoC: AXI protocol compliance /
power domain). If no domain matches, this section is empty.

## Mode B — Output Format

```markdown
## Code Review: <module_name>

### Summary
| Severity | Count |
|----------|-------|
| 🔴 Errors | X |
| 🟠 Warnings | Y |
| 🟡 Notes | Z |

### 🔴 Errors (must fix before signoff)
| # | Line(s) | Category | Issue | Fix |
|---|---------|----------|-------|-----|
...

### 🟠 Warnings (should fix; waive with justification)
| # | Line(s) | Category | Issue | Recommendation |
|---|---------|----------|-------|----------------|
...

### 🟡 Notes (informational)
| # | Line(s) | Observation |
|---|---------|-------------|
...

### Review Checklist Summary
| Category | Pass | Fail | N/A |
|----------|------|------|-----|
| Coding Style | | | |
| Latch Prevention | | | |
| FSM Integrity | | | |
| Clock/Reset/CDC | | | |
| Synthesis Readiness | | | |
| Structural Correctness | | | |
| PPA — Performance | | | |
| PPA — Power | | | |
| PPA — Area | | | |
| DFT | | | |
| Domain-Specific | | | |

### PPA Assessment
| Domain | Rating | Key Observation |
|--------|--------|-----------------|
| Performance | 🟢/🟡/🔴 | |
| Power | 🟢/🟡/🔴 | |
| Area | 🟢/🟡/🔴 | |

#### Top 3 PPA Optimization Opportunities
1. ...
2. ...
3. ...
```

---

# Mode C: Document Check (触发词: 评审文档 / 检查文档 / 阅读文档)

Cross-check technical documentation (any language) against RTL source code. Based on tape-out checklist methodology and verification review standards.

## C-1. Document Completeness

Before cross-checking, verify the document itself is complete:
- Version/date/revision history present?
- Scope clearly defined (which modules/IPs are covered)?
- References section with all cited documents accessible?
- Glossary of terms and abbreviations?
- Author/reviewer/approver identified?

## C-2. Signal Name & Port Accuracy

For EVERY signal name or port mentioned in the document:
1. Search the RTL source tree for the exact signal
2. Verify: spelling, case, direction (input / output / inout), bus indexing
3. Flag: documented but not found in RTL
4. Flag: exists in RTL but not documented (missing coverage)

## C-3. Data Width Consistency

For EVERY width/bus-size specification in documentation tables:
1. Read the actual port/parameter declaration from RTL
2. Compare: `[MSB:LSB]` ranges match?
3. Pay special attention to config-dependent widths (gated by project config macros — prefix from CLAUDE.md)

## C-4. Parameter / Register Value Accuracy

For any `parameter`, `localparam`, CSR reset value, or config define mentioned:
1. Read actual value from RTL source
2. Verify default values and valid ranges
3. Flag stale/deprecated values

## C-5. Module Hierarchy Verification

For each module name in the document:
1. Verify the Verilog/VHDL module exists in the source tree
2. Check that parent-child instantiation path is correct
3. Check that the documented hierarchy depth matches actual RTL

## C-6. Clock Domain Specification Accuracy

For clock domain tables in the document:
1. Compare frequencies against RTL clock connections and parameters
2. Verify clock domain count is accurate
3. Check that domain crossings described in doc match CDC structures in RTL
4. Verify reset domain labeling is correct

## C-7. Block Diagram / Mermaid Accuracy

For ALL diagrams (Mermaid, ASCII art, or image references):
1. Every block/label corresponds to a real module name in RTL
2. Arrow/data-flow direction matches actual signal flow in RTL
3. Grouping (subgraphs, partitions) reflects true hierarchy
4. Control/status signals shown actually exist
5. Bus widths shown in diagrams match port declarations

## C-8. State Machine Descriptions

For each FSM described in the document:
- State names match the RTL enumeration/parameters
- Transition conditions documented match the Verilog/VHDL logic
- State count is accurate
- Missing states in documentation (or vice versa)

## C-9. Cross-Reference Integrity

1. Internal links: all `[text](#anchor)` links resolve to existing sections
2. File path references: `IPs/HW/...` paths point to existing files/directories
3. External references: cited documents/specs are correctly identified
4. Figure/table references: "如图 X", "见表 Y" all resolve
5. Section references: "参见第 X 节" all correct

## C-10. Timing & Protocol Specifications

For any timing diagrams, waveform descriptions, or protocol sequences:
1. Signal sequence and handshake order match RTL implementation
2. Cycle counts (latency, throughput) match pipeline depth analysis
3. Timing constraint values (setup/hold, clock period) are physically meaningful

## C-11. Dead Link / Stale Reference Detection

- File paths that no longer exist (module was renamed or removed)
- Config macros that have been deprecated
- Module names that changed in RTL but not updated in doc
- References to external docs that changed version

## C-12. Documentation Quality

- Consistent terminology throughout (don't use 3 different terms for the same module)
- Chinese-English consistency: technical terms have consistent translations
- All abbreviations expanded on first use
- Tables are well-formatted and complete (no missing cells)
- Mermaid syntax is valid and renders correctly

## Mode C — Output Format

```markdown
## Document Check: <document_name>

### Document Profile
| Property | Value |
|----------|-------|
| File | `<path>` |
| Size | XX KB |
| RTL scope | <modules covered> |
| Last modified | <date> |

### Summary
| Category | ✓ Pass | ✗ Fail | ⚠ Warning |
|----------|--------|--------|-----------|
| Signal Names | M | K | W |
| Data Widths | M | K | W |
| Parameters/Registers | M | K | W |
| Module Hierarchy | M | K | W |
| Clock Domains | M | K | W |
| Mermaid Diagrams | M | K | W |
| FSM Descriptions | M | K | W |
| Cross-References | M | K | W |
| Timing/Protocol | M | K | W |

### 🔴 Errors (documentation contradicts RTL)
| # | Section | Doc Says | RTL Actual | Recommended Fix |
|---|---------|----------|------------|-----------------|
...

### 🟠 Warnings (likely stale or imprecise)
| # | Section | Doc Says | RTL Actual | Note |
|---|---------|----------|------------|------|
...

### 🔵 Missing Coverage (exists in RTL, not in doc)
| # | Item | RTL Location | Should Document? |
|---|------|-------------|-----------------|
...

### 📎 Broken References
| # | Section | Broken Item | Suggested Fix |
|---|---------|------------|---------------|
...

### 📝 Documentation Quality Notes
- <observations on consistency, readability, completeness>
```

---

# Mode D: RTL Code Generation & Optimization (触发词: 写代码 / 设计模块 / 优化 / 重构)

When the user wants to write new RTL, modify existing code, or optimize a module, follow this methodology.

---

## D-1. Requirements Clarification
Before writing any code, clarify:
- **Function**: What does this module need to do? Data transformation, control, protocol?
- **Interface**: What bus protocol? AHB, AXI, custom valid/ready? Clock/reset from where?
- **Throughput**: Samples per clock? Burst handling? Backpressure support?
- **Latency budget**: How many clock cycles from input to output?
- **Target frequency**: Which clock domain & target freq? (from project SDC/CLAUDE.md)
- **Configurability**: Which config macros gate this feature? (prefix from project CLAUDE.md)

## D-2. Search Existing Patterns FIRST (硬约束，写代码前必做)

**在写任何新代码之前，必须先用 `Grep`/`Glob` 搜索项目代码库的同类模块。** 通用化后不同项目约定差异大，直接套通用默认极易产出与项目风格不一致的代码。流程：

1. 搜同总线/同接口模块（如 `Grep "AXI.*awaddr"` / `Glob "**/*_fifo*.sv"`）→ 命中则**复用其端口命名、分组注释头、握手风格**，不要另起一套。
2. 搜同 FSM 风格模块（如 `Grep "typedef enum.*state"` / `Grep "localparam.*=.*'[bB]"` 找状态编码）→ 复用其状态编码（one-hot/binary/gray）、`always_ff`+`always_comb` 两段式写法、`default` 处理方式。
3. 搜同时钟域模块（`Grep "clk_<freq>"` 找同频率时钟）→ 复用其 clock/reset 命名与复位风格。
4. 搜同吞吐/延迟量级模块 → 复用其流水线深度与寄存器打拍习惯。
5. Reference project CLAUDE.md / memory for directory & naming conventions; if absent, use defaults in the "通用约定默认值" section at the end of this skill.

**范围与时间预算**：大项目（>100 模块）先搜目标模块同目录（`Glob "<同目录>/*.sv"`），无命中再扩大到全 `rtl/`；单次搜索限定文件类型（`*.sv`/`*.v`）避免命中 testbench。若三次 Grep 无命中，记"无同类模块"转通用默认，不无限扩大搜索。

**搜到则复用、搜不到才用通用默认。** 在输出的"Design Rationale"里注明：参考了哪个已有模块（`ref: <module>`）、或"无同类模块，用通用默认"。禁止跳过搜索直接凭通用默认生成。

---

## D-3. Interface Design

### D-3.0 Port Declaration Style
Design ports following industry-standard conventions (override with project CLAUDE.md if it specifies otherwise):
- Clocks and resets FIRST in port list (in that order)
- Group by functional interface with comment headers (header names from project code/CLAUDE.md; generic examples shown):
```verilog
/*****************************************************************************
* Clock/Reset
*****************************************************************************/
input  wire        rst_n,
input  wire        clk,
/*****************************************************************************
* <Interface Name>
*****************************************************************************/
```
- Use `input wire` / `output reg` / `output wire` explicitly
- Bus widths: `[MSB:LSB]` notation
- Every output port must be driven; every input port must be used

### D-3.1 Naming Conventions (Industry Best Practice)

| Category | Convention | Example |
|----------|-----------|---------|
| **File name** | MUST match module name | `mpif_fsm` → `mpif_fsm.v` |
| **Signal name** | lowercase_with_underscores | `data_in`, `clk_en`, `tx_start` |
| **Active-low** | suffix `_n` | `rst_n`, `ena_n`, `cs_n` |
| **Constants/macros/enums** | ALL_CAPS | `` `define DATA_WIDTH 32 `` |
| **Direction suffix** (optional) | `_i` / `_o` / `_io` | `axi_awaddr_i`, `i2c_sda_io` |
| **Clock/reset** | `clk` / `rst_n` (no abbreviations) | `clk_320m`, `clk_ahb` |
| **Delayed signal** | `_dN` or `_qN` suffix | `data_d1`, `data_q2` |
| **Next state** | `_next` or `_ns` suffix | `state_next`, `state_ns` |
| **Bus prefix** | Protocol abbreviation | `axi_`, `ahb_`, `apb_` |
| **Flopped/registered** | `_r` or `_ff` suffix | `data_r`, `valid_ff` |

### D-3.2 SystemVerilog `interface` Usage (Recommended Where Available)
For repeated bus protocols (AXI, AHB, etc.), use `interface` with `modport`:
```systemverilog
interface ahb_if (input logic hclk, input logic hreset_n);
    logic        hready, hsel;
    logic [31:0] haddr, hrdata, hwdata;
    logic [ 2:0] hsize, hburst;
    logic        hwrite;
    logic [ 1:0] htrans, hresp;

    modport master (output hsel, haddr, hwdata, hsize, hburst, hwrite, htrans,
                    input  hready, hrdata, hresp);
    modport slave  (input  hsel, haddr, hwdata, hsize, hburst, hwrite, htrans,
                    output hready, hrdata, hresp);
endinterface
```
**Benefits**: Single definition for all modules; `modport` enforces direction correctness at compile time.

---

## D-4. Clock & Reset Strategy

### D-4.1 Clock Discipline
- **NEVER gate clocks** — use `clken` (clock enable) instead:
```verilog
// ❌ assign gated_clk = en & clk;  // DO NOT DO THIS
// ✅
always_ff @(posedge clk or negedge rst_n)
    if (!rst_n)         data <= '0;
    else if (clken)     data <= data_in;
```
- No combinational logic on clock path
- Single `posedge` per clock domain (don't mix posedge/negedge for same clock)
- Glitch-free clock mux: use vendor primitive (BUFGMUX for Xilinx / ALTCLKCTRL for Intel / custom glitch-free cell for ASIC)

### D-4.2 Reset Strategy
- Project convention: active-low async `rst_n`
- **异步复位同步释放** (Asynchronous Assert, Synchronous Deassert):
```verilog
// Async reset assert, sync deassert
always_ff @(posedge clk or negedge rst_n)
    if (!rst_n)         state <= IDLE;
    else                state <= next_state;
```
- Every register MUST have reset
- Reset tree: module receives reset from parent, passes to children
- No internally generated resets crossing module boundaries

### D-4.3 Reset Synchronizer (for internally generated resets)
```verilog
// Reset synchronizer: async assert, sync deassert
reg rst_meta, rst_sync;
always_ff @(posedge clk or negedge ext_rst_n)
    if (!ext_rst_n) begin
        rst_meta <= 1'b0;
        rst_sync <= 1'b0;
    end else begin
        rst_meta <= 1'b1;
        rst_sync <= rst_meta;
    end
assign local_rst_n = rst_sync;
```

---

## D-5. FSM Design (Industry Standard)

### D-5.1 Encoding Selection Guide

| Encoding | FF Count | Decode Logic | Best For |
|----------|----------|-------------|----------|
| **One-Hot** | N (one per state) | Trivial (single bit test) | FPGA, high-speed, ≥8 states |
| **Binary** | log₂(N) | Complex multi-bit decode | ASIC area-sensitive, ≤8 states |
| **Gray** | log₂(N) | Moderate, glitch-resistant | CDC interfaces, FIFO pointers |

General guidance (override with project CLAUDE.md if it specifies otherwise):
- **Datapath control FSMs** (speed-critical): One-hot
- **Configuration/management FSMs** (area-sensitive): Binary
- **CDC crossing state buses**: Gray

### D-5.2 Moore vs Mealy
| | Moore | Mealy |
|--|-------|-------|
| Output timing | 1 cycle after state change | Immediate (combinational with inputs) |
| Glitch immunity | Glitch-free | Input glitches pass to outputs |
| **Default choice** | ✅ Use Moore | Only with registered outputs |

**Pro tip**: If Mealy speed is needed, add an output register → "Moore-ized" Mealy.

### D-5.3 Safe State Machine
Use `default` branch to recover from illegal/SEU-corrupted states:
```verilog
always_comb begin
    next_state = state;      // Default: stay
    case (state)
        IDLE: if (start) next_state = RUN;
        RUN:  if (done)  next_state = IDLE;
        default: next_state = IDLE;  // Safe recovery from illegal state
    endcase
end
```
Synthesis attributes for extra safety:
```verilog
(* fsm_encoding = "one_hot", fsm_safe_state = "reset_state" *)
reg [N-1:0] state;
```

### D-5.4 Two-Process FSM Template (Recommended)
```verilog
// Process 1: State register (sequential)
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        state <= IDLE;
    else
        state <= next_state;
end

// Process 2: Next-state + output logic (combinational)
always_comb begin
    // Default assignments (prevent latches)
    next_state = state;
    out_valid  = 1'b0;
    out_data   = '0;

    case (state)
        IDLE: begin
            if (start) next_state = RUN;
        end
        RUN: begin
            out_valid = 1'b1;
            out_data  = processed_data;
            if (done) next_state = DONE;
        end
        DONE: begin
            out_valid = 1'b1;
            out_data  = final_data;
            next_state = IDLE;
        end
        default: next_state = IDLE;
    endcase
end
```
**Why two-process?** Clean separation of sequential and combinational logic; tool-friendly for synthesis; easy to review.

### D-5.5 FSM Anti-Patterns to Avoid
| ❌ Anti-Pattern | ✅ Correct |
|----------------|-----------|
| `always @(posedge clk)` for next_state | `always_comb` for next_state |
| Missing `default` in case | Always include `default` → safe state |
| Outputs not assigned in all branches | Default assignments at top of always_comb |
| State register assigned in two always blocks | Single `always_ff` for state register |
| Magic number states (`3'b101`) | Named `localparam` or `enum` |

---

## D-6. Datapath Pipeline Design with PPA

### D-6.0 PPA Decision Matrix
| Decision | Performance | Area | Power |
|----------|-------------|------|-------|
| More pipeline stages | ↑ Fmax, ↑ latency | ↑ registers | ↑ clock power |
| Wider datapath | SNR/EVN↑ | ↑ gates | ↑ toggle power |
| Resource sharing | ↓ throughput | ↓ gates | ↓ leakage |
| Clock gating | — | + gating cells | ↓↓ dynamic power |
| Operand isolation | — | + and-gates | ↓↓ switching power |
| Parallel chains | ↑↑ throughput | ↑↑ gates | ↑↑ power |
| Approximate computing | — | ↓ gates | ↓↓ power |
| Coefficient reuse (FIR) | — | ↓↓ multipliers | ↓↓ power |

### D-6.1 DSP Arithmetic Design Patterns

#### Multiplier Sizing and Pipelining
| Width | Strategy | Pipeline Stages |
|-------|----------|-----------------|
| ≤8×8 | Combinational (single cycle) | 0 |
| 9-16×16 | 1 pipeline stage | 1 |
| 17-32×32 | 2 pipeline stages | 2 |
| >32 | Dedicated DSP block or iterative | N (depends) |

#### Adder Tree Pipelining
```verilog
// ❌ Unpipelined: 8-input combinational adder → deep logic, low Fmax
assign sum = a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7;

// ✅ Pipelined: 3-stage balanced tree
reg [W-1:0] stage1_0, stage1_1, stage1_2, stage1_3;  // 4 adders
reg [W-1:0] stage2_0, stage2_1;                       // 2 adders
reg [W-1:0] sum_r;                                    // 1 adder
```

#### Wallace Tree Multiplier (for ASIC)
Preferred for ASIC FIR filters: reduces partial product accumulation from O(N) to O(log N) stages.
```verilog
// Wallace tree: faster than array multiplier, smaller than Booth for moderate widths
// Use DesignWare / synthesize from `*` operator with proper constraints
```

#### Coefficient Symmetry for FIR Filters
For linear-phase FIR, symmetric coefficients halve multipliers:
```verilog
// h[0]=h[N-1], h[1]=h[N-2], ...
// Pre-add data before multiplication
assign pre_add[k] = data[addr[k]] + data[addr[N-1-k]];
assign product[k] = pre_add[k] * coeff[k];
mac <= mac + product[k];
```

#### Distributed Arithmetic (DA) — LUT-based FIR
For low-area FIR: precompute coefficient combinations into LUT, replace multipliers with table lookups.
```
DA Formula: y = Σ(Σ c[n]·x[n][b]) · 2^b  (swap summation order for LUT-based computation)
```

### D-6.2 Low-Power Coding Techniques (ROVER + Industry Practice)

#### Clock Gating
```verilog
// ✅ Register bank with clock enable (synthesis infers clock gating)
always_ff @(posedge clk or negedge rst_n)
    if (!rst_n)          cfg_reg <= '0;
    else if (cfg_update) cfg_reg <= cfg_wdata;  // Only toggles on update

// Don't use free-running enable (no clock gating inferred):
// ❌ else cfg_reg <= cfg_reg;  // Redundant, wastes power
```

#### Operand Isolation (Data Gating)
Prevents unnecessary switching in arithmetic units when output is unused:
```verilog
// ❌ Multiplier toggles every cycle (wastes power)
assign product = a * b;

// ✅ Isolate operands when result not needed
assign a_iso = (compute_en) ? a : '0;
assign b_iso = (compute_en) ? b : '0;
assign product = a_iso * b_iso;  // Zero inputs → near-zero dynamic power
```

#### Register All Outputs
Blocking glitch propagation saves cascading power:
```verilog
// ❌ Combinational output → glitches propagate downstream
assign data_out = complex_logic(data_in);

// ✅ Registered output → clean signal → downstream power saved
always_ff @(posedge clk) data_out <= complex_logic(data_in);
```

#### 2024 ROVER Framework Principles
From Imperial College/Intel research (EGRAPHS 2024): express power optimizations as local RTL rewrites:
1. **Data gating rewrite**: `assign y = f(x)` → `assign y = en ? f(x) : gated_value`
2. **Clock gating rewrite**: Free-running register → clock-enabled register
3. **Transparent register**: Bypass register when data unchanged → reduces downstream toggling
4. **Result**: Up to 33.9% total power reduction achievable through automated RTL→RTL optimization

#### Low-Power Checklist
- [ ] Config/control registers → clken gated (rarely change)
- [ ] Wide datapath buses (>64bit) → register before crossing hierarchy
- [ ] Arithmetic units → operand isolation when idle
- [ ] Memory reads → only enabled when data is needed
- [ ] Module-level idle mode → can we stop the clock?

---

## D-7. CDC Design Patterns (Multi-Clock Modules)

For multi-clock designs, follow these standard patterns:

### D-7.1 2-FF Synchronizer (Single-bit Control)
```verilog
// Standard 2-flop synchronizer for single-bit signals
reg sync1, sync2;
always_ff @(posedge dst_clk or negedge dst_rst_n) begin
    if (!dst_rst_n) begin
        sync1 <= 1'b0;
        sync2 <= 1'b0;
    end else begin
        sync1 <= src_signal;       // Source must be registered in src domain!
        sync2 <= sync1;
    end
end
assign safe_signal = sync2;
```
**Critical rules:**
- Source signal MUST be register output from source clock domain (no combinational logic)
- NO combinational logic between sync1 and sync2
- For higher MTBF (Mean Time Between Failures): add sync3 for >500MHz designs
- Use behavioral synchronizer cells from HWCOMMON (`synchronization/`) if available

### D-7.2 Pulse Synchronizer (Single-cycle pulse crossing)
```verilog
// Converts a 1-cycle pulse in src domain to a pulse in dst domain
// Uses toggle method: src pulse flips a flag, dst detects edge
reg toggle;
always_ff @(posedge src_clk) if (src_pulse) toggle <= ~toggle;

// Sync toggle to dst domain (2-FF)
reg [1:0] toggle_sync;
always_ff @(posedge dst_clk) toggle_sync <= {toggle_sync[0], toggle};

// Edge detect in dst domain
assign dst_pulse = toggle_sync[1] ^ toggle_sync[2];  // Need 3-FF for edge detect
```

### D-7.3 Handshake Synchronizer (Multi-bit data, low speed)
```
1. Src asserts req, drives data
2. Dst synchronizes req (2-FF), captures data, asserts ack
3. Src synchronizes ack (2-FF), deasserts req
```

### D-7.4 Async FIFO (Multi-bit data, high speed)
Use the project's async FIFO IP if available; otherwise design per the pattern below.

**Key design elements:**
- Dual-port RAM for data storage
- Binary → Gray code conversion for read/write pointers
- 2-FF synchronizers for crossing Gray pointers between domains
- Full flag: `wptr_gray == {~wq2_rptr_gray[MSB:MSB-1], wq2_rptr_gray[MSB-2:0]}`
- Empty flag: `rptr_gray == rq2_wptr_gray`

**FIFO depth calculation:**
```
Depth = Burst × (1 − f_read / f_write)
```
Example: f_write=200MHz, f_read=100MHz, Burst=64 → Depth = 64 × (1 − 0.5) = 32 → round to power-of-2 = 32

**Gray code conversion:**
```verilog
// Binary → Gray
assign gray = binary ^ (binary >> 1);

// Gray → Binary (iterative)
// For small pointers: implement as generate-for with XOR chain
```

### D-7.5 CDC Golden Rules Summary
| # | Rule | Violation = |
|---|------|-------------|
| 1 | Source must be registered (no combinational CDC) | Glitch-induced false sampling |
| 2 | 2-FF minimum for single-bit | MTBF too low |
| 3 | No logic between synchronizer FFs | Synchronizer failure |
| 4 | Multi-bit → Gray + 2-FF or FIFO or Handshake | Data incoherence |
| 5 | Reconvergence: sync'd paths must not recombine | Metastability-induced divergence |
| 6 | Never CDC from multiple unrelated source FFs | Inconsistent delay between bits |

---

## D-8. Coding Checklist (in-head before output)

### D-8.1 SystemVerilog Best Practices
- [ ] Use `always_ff` for sequential logic (catches multi-driver at compile time)
- [ ] Use `always_comb` for combinational logic (auto-triggers at time 0, catches incomplete sensitivity lists)
- [ ] Use `logic` type (not `reg`/`wire`) for single-driver signals
- [ ] Use `enum` / `typedef enum` for state variables
- [ ] Use `package` for shared constants, types, and functions (suffix `_pkg`)

### D-8.2 Synthesizability
- [ ] `default_nettype wire` at top of file
- [ ] No `#delay` / `initial` / `$display` / `$random` in synthesizable blocks
- [ ] No `fork/join` / `wait` / `force/release` in synthesizable blocks
- [ ] No hierarchical references (`.` or `/` paths)
- [ ] No recursive module instantiation
- [ ] `// synthesis translate_off/on` guards around simulation-only code

### D-8.3 Latch Prevention
- [ ] `always_comb`: all outputs assigned default values at TOP before conditionals
- [ ] `case` has `default` branch
- [ ] `if-else` chains have final `else`
- [ ] `always_ff`: non-blocking `<=`; `always_comb`: blocking `=`
- [ ] NEVER mix blocking and non-blocking in same always block
- [ ] Functions/tasks: every output assigned in ALL branches (no incomplete-assignment latch inference — mirrors B-2 #6)

### D-8.4 Structural Correctness
- [ ] Module header comment block with description
- [ ] `parameter`/`localparam` declarations before ports
- [ ] Ports grouped by functional interface with comment headers
- [ ] No magic numbers → all named as `localparam`
- [ ] All submodule instances use named port connections (`.port(signal)`)
- [ ] All output ports driven; all input ports used
- [ ] Bit-widths match in ALL assignments (LHS width = RHS width)
- [ ] No multi-driver nets
- [ ] No combinational feedback loops

### D-8.5 Clock & Reset
- [ ] Reset leg in all `always_ff` blocks
- [ ] No gated clocks → `clken` instead
- [ ] Multi-clock module → CDC synchronizers present and correct
- [ ] Outputs registered (blocks glitch propagation)

### D-8.6 Code Formatting
- [ ] **4 spaces indentation** (NO tabs)
- [ ] Spaces around operators: `a + b`, not `a+b`
- [ ] Port declarations aligned in columns
- [ ] One statement per line
- [ ] Line width ≤100 characters (break and align long expressions)

---

## D-9. Optimization Mode (触发词: 优化 / 改代码 / 重构)

### D-9.1 Optimization Mindset
> "Profile first, optimize second." Don't optimize without understanding the bottleneck.

### D-9.2 PPA Triage Matrix

| Bottleneck | Analysis | Solutions (best → fallback) |
|-----------|----------|---------------------------|
| **Fmax too low** | Deepest combinational path; high fan-out nets | 1. Pipeline at bottleneck 2. Balance uneven stages 3. Register high-fan-out signals 4. Restructure large MUX trees 5. Use faster arithmetic (Wallace tree → CLA) |
| **Latency too high** | Pipeline depth larger than needed | 1. Merge adjacent pipeline stages 2. Use combinational for shallow logic 3. Parallelize independent operations |
| **Area too large** | Gate count dominant in arithmetic or registers | 1. Resource-share arithmetic (time-multiplex) 2. Trim unused datapath bits 3. Serialize parallel chains 4. Coefficient reuse (FIR) 5. DA instead of multiplier-based (FIR) |
| **Power too high** | High toggle rate on wide buses; free-running clocks | 1. Add clock gating on register banks 2. Operand isolation on arithmetic 3. Register module outputs 4. Reduce datapath width where SNR allows 5. Memory sleep mode when idle |
| **Throughput too low** | Pipeline bubbles; serial processing | 1. Remove unnecessary backpressure 2. Parallelize independent chains 3. Widen datapath 4. Use double-buffering to hide latency |

### D-9.3 Quantitative Estimation
Before optimizing, estimate the impact:

| Change | Fmax Impact | Area Impact | Power Impact |
|--------|------------|-------------|--------------|
| +1 pipeline stage | +15-30% | +5-10% (FFs) | +3-8% (clock) |
| Clock gating (50% regs) | -2-5% (setup) | +1-2% (cells) | -20-40% (dynamic) |
| Operand isolation | -2-5% | +3-7% (and-gates) | -15-30% (switching) |
| Resource sharing (2→1) | -5-15% | -30-40% | -20-30% |
| Register outputs | +2-5% (1 cycle) | +1-3% | -10-20% (downstream) |
| Width reduce 16→12 bit | +5-10% | -20-25% | -20-25% |

### D-9.4 Optimization Report Format
```markdown
## Optimization: <module>
### Profile
| Metric | Before | Bottleneck? |
|--------|--------|-------------|
| Est. Fmax | X MHz | |
| Latency | N cycles | |
| Area (regs+gates) | ~N | |
| Power hotspot | <description> | |

### Changes
| # | Change | P | A | Pwr | Rationale |
|---|--------|---|---|-----|-----------|

### Result
| Metric | Before | After | Δ |
|--------|--------|-------|-----|
```

---

## D-10. Generated Code Output Format

```markdown
## Module: <module_name>

### Design Rationale
- **Language**: SystemVerilog / Verilog (match project convention)
- **Function**: <1-sentence>
- **Clock**: <freq>, **Reset**: rst_n (async assert, sync deassert)
- **Latency**: <N cycles>, **Throughput**: <1 per M cycles>
- **PPA Design Choices**: <key trade-offs made>

### Interface
| Port | Dir | Width | Category | Description |
|------|-----|-------|----------|-------------|

### Architecture Diagram
\`\`\`mermaid
flowchart LR
  subgraph clk_domain [Clock: <freq>]
    input --> stage1["Stage 1<br/>(desc)"] --> stage2["Stage 2<br/>(desc)"] --> output
  end
\`\`\`

### FSM (if applicable)
\`\`\`mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> ACTIVE: start
  ...
\`\`\`

### PPA Estimate
| Metric | Estimate | Notes |
|--------|----------|-------|
| Est. Fmax | ~X MHz | @ target corner |
| Latency | N cycles | input → output |
| Throughput | 1 per M cycles | |
| Register Count | ~N | |
| Arithmetic | M mult(W×W) + K add(W) | |
| Memory | W×D (type) | |
| Clock Gating | ~X% registers gated | |
| Outputs Registered | Yes/No/Partial | |

### Verilog Code
\`\`\`verilog
\`default_nettype wire
module <name> #(
    parameter ...
) (
    // Clock/Reset
    input  wire        rst_n,
    input  wire        clk,
    // Interface
    ...
);
    // Local parameters
    localparam IDLE = ...
    // Internal signals
    logic ...
    // =========== Sequential logic ===========
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) ...
        else ...
    end
    // =========== Combinational logic ===========
    always_comb begin
        // defaults
        ...
    end
endmodule
\`\`\`

### Compliance Checklist
| # | Rule | Status |
|---|------|--------|
| 1 | `always_ff` for sequential, `always_comb` for combinational | ✓ / N/A |
| 2 | Blocking (=) in comb, non-blocking (<=) in seq, never mixed | ✓ |
| 3 | Default values at top of `always_comb` | ✓ |
| 4 | `case` has `default`, `if-else` has final `else` | ✓ |
| 5 | All outputs assigned in all branches (no latches) | ✓ |
| 6 | Reset on all sequential registers | ✓ |
| 7 | No `#delay`/`initial`/`$display` in synthesizable code | ✓ |
| 8 | Named port connections (`.port(signal)`) | ✓ |
| 9 | All bit-widths match in assignments | ✓ |
|10 | No multi-driver nets | ✓ |
|11 | Outputs registered (where latency allows) | ✓/N/A |
|12 | Clock gating applied to config/rarely-changing registers | ✓/N/A |
|13 | CDC synchronizers present for cross-domain signals | ✓/N/A |
|14 | No gated clocks (use `clken`) | ✓ |
|15 | 4-space indentation, operators spaced, aligned ports | ✓ |
```

---

# Mode E: RTL → Documentation (触发词: 生成文档 / 逆向文档 / 文档对齐 / 增量更新文档)

根据 RTL 代码生成或维护设计文档。覆盖三个真实场景，按 args 关键词分流：

| 子模式 | 触发关键词 | 场景 | 输入 | 输出 |
|--------|-----------|------|------|------|
| **E-1 逆向文档** | 逆向文档, 补文档, 生成文档, reverse-document | 无文档/遗留代码，从 RTL 生成完整设计文档 | RTL 文件 | 完整设计文档（新建） |
| **E-2 漂移对齐** | 文档对齐, 漂移对齐, 重新生成文档 | 有文档但与代码漂移，以 RTL 为准重生成 | RTL + 旧文档 | 对齐后的文档（覆盖旧文档漂移段落） |
| **E-3 增量更新** | 增量更新文档, 更新文档, doc delta | 代码改了 diff，只更新文档对应段落 | RTL diff + 文档 | 文档增量 patch（仅改动段落） |

## 与 Mode A/C/D 的区分（重要，勿混用）

- **Mode A** = 分析报告，**诊断体裁**（"我发现了什么"，含问题指出、可疑模式、PPA 优化建议）→ 给工程师看代码质量
- **Mode C** = 文档核对，**比对体裁**（"文档说 X，代码是 Y，不一致"）→ 只报差异，不改文档
- **Mode D** = 设计+实现，**做决策**（选编码、定流水线深度、写可综合代码）→ 产出代码，有权做设计取舍
- **Mode E** = 事实提取+成文，**不做决策**（只描述代码已实现的事实，设计意图标`【待确认】`交还）→ 产出文档，无权做设计取舍

Mode E 复用 Mode A 的分析能力提取素材，但**输出体裁切换为规格**：去掉诊断语气，补齐接口契约表，按文档模板组织。Mode E 可在内部先跑一遍 Mode A 提取事实，再成文。**Mode E vs Mode D 的关键区别**：D 能做设计决策（"这里选 one-hot 因为…"），E 不能（"状态编码为 one-hot【设计意图未在代码体现，待确认】"）——E 永远不替设计者拍板。

## E-0. 通用约束（三个子模式共用）

### 事实优先，禁止臆测设计意图
- 文档**只描述代码已实现的事实**（接口、时序、FSM、数据通路、寄存器）。
- 设计意图（"为什么这么设计""考虑过哪些方案""取舍理由"）**无法从代码确定**——这类内容必须标 `【设计意图未在代码体现，待确认】`，交还设计者补，**不得编造**。
- 这是 Mode E 与 Mode D（写代码）的根本区别：Mode D 可以做设计决策，Mode E 只做事实提取+成文，决策权在设计者。

### 项目上下文加载
- 先按"项目上下文加载"读项目 CLAUDE.md / memory：文档模板、术语表、已有文档风格。
- 文档语言：跟随项目已有文档语言（E-2/E-3 有旧文档时跟随其语言；E-1 无旧文档时跟随项目主文档语言或用户 prompt 语言）。
- 若项目有文档模板（如 `docs/template/module-spec.md`），按模板组织；无模板用下方 E 输出格式。

### 素材提取（内部步骤，复用 Mode A）
成文前先对目标 RTL 跑一遍 Mode A 的 A-1~A-12 全量提取：模块标识/参数/端口/时钟域/复位/FSM/数据通路/子模块/寄存器（A-1~A-9）+ 架构图（A-10）+ PPA 估计（A-12）。提取结果作为文档事实来源，**逐项与代码核对**（Grep/Read），确保文档每个断言都有代码行号支撑。E 输出 §8 架构图、§9 PPA 特征分别依赖 A-10、A-12 素材。

## E-1. 逆向文档（reverse-document）

**场景**：遗留代码 / 开源 IP / 无文档模块，从 RTL 生成完整设计文档。

### 流程
1. Read 目标 RTL 全文 + 其实例化的子模块（追一层）。
2. 跑 Mode A 素材提取（A-1~A-12 全量），逐项核对代码行号。
3. 按"Mode E 输出格式"生成完整文档。
4. 设计意图类内容标 `【设计意图未在代码体现，待确认】`，在文末汇总成"待确认清单"。
5. 若代码有明显但未文档化的约束（如某参数有隐含上下界），标注 `【代码隐含约束，待确认是否 spec 要求】`。

### 输出落点
- 支持可选 `--out <path>` 指定输出路径（如 `逆向文档 rtl/xxx.sv --out docs/xxx.md`）。
- 未指定 `--out` → 默认写到 `docs/<module_name>.md`（或项目文档目录约定路径）。
- 若已存在同名文档 → 转为 E-2 漂移对齐（不覆盖，先比对）。

## E-2. 漂移对齐（realign drifted doc）

**场景**：有文档但与代码漂移（改了 RTL 忘改文档），以 RTL 为准重新生成漂移段落。

### 流程
1. Read 旧文档 + 目标 RTL。
2. 内部跑一遍 **Mode C**（文档核对）列出所有漂移点（文档说 X、代码是 Y）。
3. 对每个漂移点，**以代码为准**重新生成对应文档段落。
4. 保留旧文档的**未漂移段落**和**设计意图类内容**（代码改不动设计理由）——只改事实性漂移。
5. 输出对齐后的完整文档 + 一份"漂移修正清单"（哪些段落改了、为什么）。

### 关键约束
- 漂移对齐**只修事实性漂移**（信号名/位宽/参数/FSM 状态/寄存器值），**不改写设计意图段落**（那不是漂移，是原始设计说明）。
- 若旧文档某段是纯设计意图（如"选择二进制编码是因为面积优先"），代码无法验证也不否定 → 保留原样，不标待确认（设计意图本就靠人补，漂移对齐不负责补）。
- 输出落点：覆盖原文档（in-place Edit 漂移段落），或写 `<doc>.aligned.md` 由用户确认后替换。

## E-3. 增量更新（incremental update）

**场景**：代码刚改了一个 diff（新功能/重构/修 bug），只更新文档受影响段落，不动其余。

### 流程
1. 获取代码 diff（`git diff` 或用户指定改动文件/段落）。
2. 分析 diff 影响哪些文档维度：端口变 → 接口表；FSM 变 → 状态机段；参数变 → 参数表；数据通路变 → 架构图+时序段；寄存器变 → 寄存器映射。
3. Read 现有文档对应段落 + 改动后代码。
4. **只重生成受影响段落**，未受影响段落原样保留。
5. 输出文档 patch：列出改了哪些段落、对应代码 diff 的哪部分。

### 关键约束
- 增量更新**只动受影响段落**，禁止顺手改其他段落（避免引入非 diff 相关的改动，便于审查）。
- 若 diff 引入全新设计意图（如新增某功能的设计理由），标 `【新增功能设计意图，待确认】`，不编造。
- 输出落点：in-place Edit 受影响段落；同时输出一份"文档变更说明"（哪些段、对应代码 diff）。

## Mode E — 输出格式（设计文档体裁）

```markdown
# <Module Name> 设计文档

> 来源：RTL 逆向生成（Mode E-<子模式>） · 生成日期 · RTL 版本 <git commit>
> 待确认项见文末"待确认清单"

## 1. 概述
- **功能**：<一句话，从代码模块头注释+端口推断；无注释则标【功能描述待确认】>
- **语言/文件**：SystemVerilog / `<path>`
- **在层级中的位置**：<父模块> 实例化本模块（已 Read 父模块确认）

## 2. 接口规格
| Port | Dir | Width | Category | Description |
|------|-----|-------|----------|-------------|
（按功能分组：Clock/Reset、总线接口、控制/状态、数据通路；每组来自代码注释头，填入 Category 列）

> 多时钟域模块：在 Description 列标注端口所属时钟域（如 `clk_axi, AXI write address`）；单时钟域模块填 `clk` 或省略。

- **总线协议**：AXI4-Lite / AHB-Lite / 自定义 valid-ready / 直连（已核对代码握手信号）
- **握手**：<valid/ready 对、req/ack 对，列全>
- **中断/唤醒**：<列出，无则写"无">

## 3. 参数与配置
| 参数 | 默认值 | 可覆盖? | 描述 | 隐含约束 |
|------|--------|---------|------|----------|
（"隐含约束"列：代码中虽未显式约束但有上下界/依赖的，标【待确认是否 spec 要求】）

## 4. 时钟与复位
| 时钟 | 标称频率 | 驱动逻辑 | CDC? |
|------|---------|---------|------|
（频率从项目 CLAUDE.md/SDC 取；未指定标"未在项目上下文指定"）

- **复位**：<异步/同步，有效电平，命名，已核对所有 always_ff 复位腿>
- **CDC 路径**：<每条标注 src→dst、同步方案、深度；无则"无跨域">

## 5. 状态机
（每个 FSM 一段）
### FSM: <name>
- **编码**：one-hot / binary / gray（N 位）
- **状态表**：

| 状态 | 编码 | 描述 | 入口条件 | 出口条件 |
|------|------|------|----------|----------|

- **状态转移图**：（Mermaid stateDiagram-v2）
- **安全恢复**：default → <状态>（已核对 default 分支）

## 6. 数据通路
- **流水线深度**：N 级（已数寄存器级数）
- **吞吐**：1 sample / M cycles（已找瓶颈级）
- **关键运算**：<乘法器 W×W、加法树 N 输入、移位器...>
- **存储**：<FIFO/SRAM 实例：宽×深，已核对实例化>
- **饱和/舍入**：<SatSigned/Round 策略，已核对代码>

## 7. 寄存器映射（如有 CSR）
| 偏移 | 寄存器 | 位域 | 访问 | 复位值 | 描述 |
（已核对代码复位值与位域定义）

## 8. 架构图
（Mermaid flowchart：输入→处理级→输出，时钟域着色）

## 9. PPA 特征
（从代码结构估计，工艺/器件从项目上下文取；未指定标 @unspecified process）
| 维度 | 评估 | 依据 |
|------|------|------|
| 时序 | 🟢/🟡/🔴 | <关键路径逻辑级数> |
| 功耗 | 🟢/🟡/🔴 | <门控覆盖率、空闲态> |
| 面积 | 🟢/🟡/🔴 | <寄存器/算子/存储估算> |

## 10. 待确认清单（Mode E 专属，交还设计者）
- [ ] §1 功能描述：代码无模块头注释，待确认
- [ ] §3 参数 X 隐含上下界 1~N：代码隐含约束，待确认是否 spec 要求
- [ ] §6 乘法器位宽选择 16-bit：设计意图未在代码体现，待确认
- ...
```

## Mode E — 子模式追加段

**E-2 漂移对齐**在文末追加：
```markdown
## 漂移修正清单
| 段落 | 旧文档 | 代码实际（行号） | 修正 |
（仅事实性漂移；设计意图段落不在此列）
```

**E-3 增量更新**在文末追加：
```markdown
## 文档变更说明（对应代码 diff）
| 文档段落 | 代码 diff 位置 | 变更摘要 |
（仅受 diff 影响段落）
```

## Mode E — 失败模式与避免

- **臆测设计意图**：编造"为什么这么设计" → 禁止，标`【待确认】`交还。
- **E-2 误改设计意图段落**：把原始设计说明当漂移改掉 → 只改事实性漂移，设计意图段落保留。
- **E-3 顺手改未受影响段落**：引入非 diff 相关改动 → 只动受影响段落，便于审查。
- **素材未核对**：直接凭印象写接口表 → 每个断言必须有代码行号支撑（Grep/Read）。
- **覆盖已有文档未确认**：E-1 见同名文档应转 E-2，不静默覆盖。

---

# 通用约定默认值（项目无 CLAUDE.md / memory 时的回退）

当"项目上下文加载"未从项目文件取到约定时，用以下通用默认。这些是 ASIC/FPGA 行业最佳实践，与上文 D-3.1 / D-8 的检查项一致，集中于此便于回退引用。

## 复位与时钟
- 复位：**异步复位、同步释放**（async assert, sync deassert），`always_ff @(posedge clk or negedge rst_n)`
- 复位有效电平：**低有效**，命名 `rst_n`（高有效须注释 `// active high`）
- 每个时钟域**独立**复位信号，禁止跨域共享复位
- 禁止门控时钟，用 `clken`（clock enable）替代
- 同一时钟域不混用 `posedge`/`negedge`
- 时钟 mux 用 vendor primitive（Xilinx BUFGMUX / Intel ALTCLKCTRL / ASIC 自定义无毛刺 cell）保证无毛刺

## 命名
- 信号：`lowercase_with_underscores`
- 低有效：`_n` 后缀（`rst_n`, `cs_n`）
- 常量/宏/枚举：`ALL_CAPS`
- 方向后缀（可选）：`_i` / `_o` / `_io`
- 时钟/复位：`clk` / `rst_n`（不缩写），如 `clk_200m`, `clk_axi`
- 打拍信号：`_dN` / `_qN`（`data_d1`）
- 次态：`_next` / `_ns`
- 总线前缀：协议缩写（`axi_`, `ahb_`, `apb_`）
- 寄存器输出：`_r` / `_ff`
- 文件名 = 模块名（`mpif_fsm` → `mpif_fsm.v`）

## 编码风格
- 时序逻辑 `always_ff` + 非阻塞 `<=`；组合逻辑 `always_comb` + 阻塞 `=`；同一 always 块内禁止混用
- SV 用 `logic`（单驱动信号），不用 `reg`/`wire`
- 状态变量用 `typedef enum`
- 共享常量/类型/函数放 `package`（后缀 `_pkg`）
- `case` 有 `default`，`if-else` 有最终 `else`，组合块顶部先给默认值（防 latch）
- 4 空格缩进（禁止 tab），运算符两侧空格，端口声明列对齐，行宽 ≤100

## 综合
- `default_nettype wire` 置文件顶
- 可综合块内禁止 `#delay` / `initial` / `$display` / `$random` / `fork-join` / `wait` / `force-release` / 层次引用 / 递归实例化
- 仿真专用代码用 `// synthesis translate_off/on` 包裹

## 接口
- 端口顺序：clocks/resets 先，再总线接口，再控制/状态，再数据通路
- 子模块实例化用命名端口连接（`.port(signal)`）
- 所有输出端口必须驱动，所有输入端口必须使用
- 赋值左右位宽一致；显式符号扩展（`$signed`）vs 零扩展

---

# 领域扩展（pluggable，按项目上下文叠加）

每个领域一节，含**触发关键词** + **PPA 专项** + **协议/功能专项**。项目上下文命中某领域时，将其检查项叠加到 Mode A/B 相应小节（A-12 PPA、B-7 PPA、B-9 功能）。

## 如何新增一个领域

按以下三段式模板，在末尾追加 `## 领域扩展·<名称>` 节即可，无需改动主框架：

```
## 领域扩展·<领域名称>

**触发关键词**：<中英文关键词，逗号分隔，用于项目上下文命中匹配>

### PPA 专项（叠加到 B-7.5）
- <子模块/算子>：<设计权衡点，A vs B vs C>

### 协议/功能专项（叠加到 B-9）
- <spec 一致性检查项>
```

要点：
1. **触发关键词**要包含该领域足够 distinctive 的词（避免与通用词混淆），中英文都列。
2. **PPA 专项**写该领域特有的算子/存储/带宽权衡（通用 PPA 已在 A-12/B-7 覆盖，勿重复）。
3. **协议/功能专项**写该领域 spec 合规检查。
4. 同步在"项目上下文加载"的命中规则里加一行 `关键词 → 领域扩展·<名称>`。

现有领域：WiFi/802.11、视频编解码、网络/通信、SoC/总线、AI/NPU 计算。可按此模板增补 DSP/音频/存储控制器/安全加密引擎 等。

## 领域扩展·WiFi / 802.11

**触发关键词**：WiFi、802.11、PHY、MAC、SIFS、DIFS、OFDM、RW_NX、AGC、CCA、RIU、MLO

### PPA 专项（叠加到 B-7.5）
- **FFT/IFFT**：radix 选择 vs 吞吐需求；流水线 vs 迭代？
- **LDPC Decoder**：迭代次数 vs 延迟预算 vs 面积；提前终止逻辑？
- **Equalizer**：矩阵求逆规模 vs 信道带宽配置；吞吐缩放？
- **Beamforming (SVD)**：Jacobi 迭代次数 vs 收敛；精度 vs 面积？
- **Filter chains**：半带滤波器抽头数 vs 阻带衰减 vs 面积？
- **Deinterleaver**：存储规模 vs 各 802.11 模式最大块大小？

### 协议/功能专项（叠加到 B-9）
- Config 宏一致性：`RW_NX_*` 门控的特性跨层级一致
- DSP 链：valid/ready 握手协议正确实现
- 802.11 时序：帧间间隔（SIFS/DIFS）相关逻辑正确
- 多链路（MLO）：link index 线正确参数化与连接
- 加密流水线：密码模式选择（AES/CCM/GCM/SM4）正确路由
- RIU 接口：AGC/CCA 信号时序符合 spec

## 领域扩展·视频编解码（H.264 / H.265）

**触发关键词**：H.264、H.265、HEVC、codec、CTU、CU/PU/TU、运动估计、运动补偿、CABAC、CAVLC、去块滤波、SAO、DPB、行缓冲

### PPA 专项
- **运动估计（ME）**：搜索窗大小 vs IME/FME 级数 vs 周期/块；SAD/ SATD 算子并行度
- **运动补偿（MC）**：插值滤波器（H.265 8抽头 luma / 4抽头 chroma）流水线；参考帧读取带宽
- **变换/量化**：整数 DCT/DST 核心变换规模；QP 依赖量化；RDOQ 面积 vs 精度
- **熵编码**：CABAC context model 存储；binarization 表；二进制算术编码器吞吐（bin/cycle）
- **去块滤波 / SAO**：边界强度计算；行缓冲深度 vs 并行 CTU 行数
- **参考帧 / DPB**：DPB 容量 vs 最大参考帧数 vs 分辨率；外部带宽预算
- **行缓冲**：相邻 CTU 行数据复用，行缓冲 SRAM 深度 vs 并行度
- **吞吐预算**：像素吞吐 = 分辨率 × 帧率；CTU/s = 像素吞吐 / CTU 像素数；每 CTU 周期数 vs 目标频率

### 协议/功能专项
- 参考帧管理（POC/DPB 更新）与 spec 一致
- Slice/NAL 头解析正确
- 帧内预测模式与参考样本构造符合 normative 文本
- 半像素/四分之一像素插值系数正确
- 环路滤波边界判定与标准一致

## 领域扩展·网络 / 通信（以太网 / SerDes）

**触发关键词**：Ethernet、以太网、MAC、PCS、PMA、1588、SerDes、CRC、FEC、KP/KR、TSN

### PPA 专项
- **MAC**：线速（10/25/40/100/400G）下每周期字宽 vs 频率；包缓冲 SRAM 带宽
- **PCS**：64b/66b 编解码；block 同步状态机；gearbox 位宽转换
- **FEC（IEEE 802.3 KP/KR）**：RS-FEC 纠错能力 vs 延迟；交织深度
- **CRC**：多项式与 spec 一致（CRC-32 Ethernet）；并行 CRC 实现 vs 串行
- **Timestamp（1588）**：时间戳精度（sub-ns）；时钟域（实时钟 vs 数据钟）
- **SerDes 对齐**：bit/word align 状态机；comma 检测

### 协议/功能专项
- 帧间隙（IPG）合规
- 暂停帧/流控（IEEE 802.3x / PFC）正确
- 自协商 / Link Training 状态机
- 包整形（shaper）令牌桶参数

## 领域扩展·SoC / 总线（AXI / AHB / APB）

**触发关键词**：SoC、AXI、AHB、APB、interconnect、arbiter、QoS、UPF、power domain、cache coherence、outstanding

### PPA 专项
- **Interconnect**：仲裁器规模 vs outstanding 数；地址译码 fanout
- **总线宽度**：数据通道宽度 vs 目标带宽 vs 频率
- **缓冲**： outstanding buffer 深度 vs 面积；register slice 插入改善时序
- **功耗域**：可关电域边界；isolation cell；retention register

### 协议/功能专项
- AXI：VALID/READY 握手、4KB 边界、burst 类型、exclusive access、outstanding ID
- AHB：HTRANS 编码、HREADY 流水线时序、HRESP 错误握手
- APB：两阶段（setup/access）时序、PErrror
- 地址译码：slave 选择逻辑、默认从设备
- 功率域：UPF isolation/level-shifter 正确；复位/时钟跨功率域同步
- cache coherence：MESI/MOESI 状态机、snoop 响应

## 领域扩展·AI / NPU 计算

**触发关键词**：NPU、AI accelerator、矩阵乘、matrix multiply、systolic array、PE 阵列、量化、INT8、FP8、tiling、MAC 利用率、稀疏

### PPA 专项
- **矩阵乘单元**：systolic array 规模（M×N×K）vs 频率 vs 面积；PE 复用
- **量化**：INT8/INT4/FP8 乘加器位宽 vs 精度 vs 面积；累加器位宽防溢出
- **片上 SRAM**：权重/激活/输出 SRAM 切分 vs 带宽；bank 数 vs 冲突
- **数据复用（tiling）**：weight stationary / output stationary / row stationary；片外带宽 vs MAC 利用率
- **稀疏化**：结构化稀疏 skip-zero 逻辑 vs 非结构化索引；面积开销 vs 功耗收益
- **吞吐**：峰值 TOPS = MAC 数 × 频率 × 2 / 量化位宽；实际 MAC 利用率 vs 峰值

### 协议/功能专项
- 数据流（NHWC/NCHW/自定义 layout）布局一致
- 量化 scale/zero-point 应用顺序正确
- 激活函数（ReLU/GELU/Sigmoid）定点实现精度
- DMA weight prefill 与计算流水线重叠

---

# 维护说明

## 改动原则

- **Mode A/B/C/D 四模式结构 + 触发词表 + 输出格式模板 = 稳定**，勿轻易改——下游 ab-review 依赖 Mode B/C 关键词（"评审代码/评审文档"）与输出格式。
- **通用部分**（A-12/B-7 PPA 方法论、B-1~B-6 编码/latch/FSM/CDC/综合/结构、D-4~D-8 CDC/FSM/流水线模板）= 行业标准，改动需谨慎。
- **可自由增补**：领域扩展节（按"如何新增一个领域"模板）、通用约定默认值（项目无约定时的回退）。
- **泛化铁律**：主框架不得再引入任何项目/领域专属硬编码（WiFi/视频/某厂工艺等）；领域专属内容只放"领域扩展"节，由项目上下文命中后叠加。

## 版本

- 泛化版：主框架 ASIC/FPGA 通用 + 5 领域扩展（WiFi/视频/网络/SoC/AI）+ 项目上下文加载 + 通用约定默认值。
- 后续改动建议在文末或 CHANGELOG 记录，不破坏 Mode 结构。

## 回归测试（改了检查清单/格式后）

自测脚本不适用（rtl-analyze 无 state 机，不像 ab-review 有 `_ab_split_selftest.py`）。改后靠**人工跑一例**验证：

1. **Mode A**：挑一个项目模块，`Skill(skill="rtl-analyze", args="分析代码 rtl/xxx.sv")`，检查输出含 A-1~A-12 各小节 + Mermaid 图 + PPA 估计带工艺标注。
2. **Mode B**：`args="评审代码 rtl/xxx.sv"`，检查输出含 severity 汇总表 + Errors/Warnings/Notes 三段 + checklist 汇总。
3. **Mode C**：`args="评审文档 docs/xxx.md"`，检查输出含文档 profile + 9 类检查汇总 + 错误/警告/缺失/断链四段。
4. **领域叠加**：在 WiFi 项目跑 Mode B，确认 B-7.5/B-9 出现 WiFi 专项；在无领域特征项目跑，确认 B-7.5/B-9 为空指引。
5. **Skill 调用不反问**：`Skill()` 调用带模糊 args 时应默认 Mode A 执行并标注"⚠ 模式未显式指定"，不应反问。

任一项输出格式残缺或反问，说明改动破坏了 Mode 结构，需回退。