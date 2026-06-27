---
name: ab-review
description: "A/B 双角色多轮审阅-修改工作流，全自动迭代直到 B 终审通过。A=执行修改，B=审阅挑刺，交替推进。触发词：\"AB审阅\"、\"A/B 审阅\"、\"双角色审阅\"、\"多轮审阅修改\"、\"文档审阅\"、\"review document iteratively\"、\"critic-revise loop\"。典型用法 \"AB审阅：对 design-note.md 执行 A/B 多轮审阅，B 终审为止\"。适用于技术文档、设计说明、RTL 代码的深度审阅与逐轮修订；RTL 对象自动叠加 rtl-analyze（B 角色用 Mode B 评审代码 / Mode C 评审文档；A 角色用 Mode E 生成/对齐/增量更新文档）。支持 --split 双终端模式：A/B 分跑两个进程（可不同模型），经 .ab-review/state.json 标志文件 + 定时轮询自动乒乓，无需人工中转。"
user-invocable: true
argument-hint: "[文档或RTL路径] [可选: --split --role a|b [--init]] [可选: 范围如 第3-5节]"
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Skill, Agent
metadata:
  type: workflow
  domain: documentation
---

# AB审阅 — A/B 双角色多轮审阅修改工作流

## Purpose

对一份文档或 RTL 代码执行**全自动、多轮、闭环**的审阅-修改迭代：
- **B 角色（审阅者）**：以"完全没看过代码的开发者"视角，指出具体位置的理解障碍。
- **A 角色（修改者）**：只能依据代码或文档已有事实修改，不得臆造；无法验证的标注`【待验证】`。
- 两角色在同一回答内交替，直到 B 输出终审通过信号或达到轮次上限。

所有轮次在**同一次回答内**自动完成，中途不等待用户输入。

## Use_When（触发条件）

- 用户说 "AB审阅"、"A/B 审阅"、"双角色审阅"、"多轮审阅修改"
- 用户要对一份文档/代码做"深度审阅 + 逐轮修订"，而非一次性 review
- 用户明确要求"B 终审为止"或"改到没问题为止"

## Do_Not_Use_When

- 纯代码 bug 定位/修复 → 用 `/code-review` 或 `/rtl-agent-team:rtl-bug-repro`
- 一次性小改、单点检查 → 直接 review，无需多轮闭环
- 对象不是文档也不是 RTL（如配置文件、构建脚本）→ 不适用
- 用户要的是"生成新文档"而非"审阅已有文档" → 用 doc-coauthoring

## Invocation（两种触发方式等价）

**方式 1 — 斜杠命令**：
```
/ab-review design-note.md
/ab-review rtl/wifi_phy/top.sv
/ab-review design-note.md 第3-5节
```

**方式 2 — 自然语言**（description 含触发词，harness 会路由到本 skill）：
```
AB审阅：对 design-note.md 执行 A/B 多轮审阅，B 终审为止。
```

若只给指令不含具体标准，按本文档"默认审阅标准"执行。

## Inputs（路径与读写语义）

1. **路径解析**：`$ARGUMENTS` 第一个参数为目标路径，相对当前工作目录解析。
   - 找不到 → **fail-fast**，输出 `ERROR: 找不到文档 <path>` 并停止，不臆测路径。
   - 路径指向目录 → 询问用户指定具体文件，或按目录内主文档（README/design-note/*.md）自动选取并告知。
2. **范围参数**（可选）：如 `第3-5节`、`§4`、`行 100-200`。给出则只审阅该范围；未给出按规模自适应策略。
3. **A 修改落点（默认 in-place）**：
   - 默认直接 `Edit` 原文件。修改前先 `Read` 全文，每条修改用唯一 `old_string` 精确替换。
   - 用户加 `--copy` 标志 → 改写到 `<name>.reviewed.md`，原文件不动。
   - RTL 代码修改同样 in-place，但必须先确认在 git 工作树内（避免破坏未提交改动）；不在 git 仓库则警告并要求确认。

## 配套 RTL 源前置检查（按对象分类走不同强度）

**目的**：审阅文档/代码前先识别"是否需要配套文件"，按需配对，避免"光审文档没核对代码"或"为独立教程文档瞎找代码"导致审阅失真。

**前置：对象分类**

按 target 文件名/扩展名分 4 类（由框架层 `classify_target` 实现，详见 `drivers/_project.py`）：

| 分类 | 典型文件 | 协议强度 |
|---|---|---|
| `rtl` | `top.sv` / `xxx.v` | 走 rtl-analyze 协议（建议+提醒），不归本节管 |
| `doc-with-code` | `CordicVect_analysis.md` / `模块设计说明.md` / `xxx_design.md` / `xxx_spec.md` / `xxx_review.md` | **强制**：必须找到配套代码；找不到 → 阻塞 `[y/n/p]` |
| `standalone-doc` | `学习手册.md` / `tutorial.md` / `教程.md` / `notes.md` / `cheatsheet.md` / `概览.md` / `faq.md` | **跳过**：完全不配对；B 角色直接审 |
| `unknown-doc` | `foo.md`（无法判定） | 保守按 `doc-with-code` 协议（强制+阻塞） |

CLI 可显式覆盖：`--doc-class {with-code,standalone}`。

**仅对 `doc-with-code` / `unknown-doc` 执行下方流程**；`standalone-doc` 直接进入正式审阅。

**执行顺序**（任一命中即停止，否则进入下一步）：

1. **文档内引用**：读 target 文档，提取所有指向代码文件的引用：
   - 行内代码块 `` `path/to/foo.sv` ``
   - 围栏代码块 ` ``` ... ./relative/path ... ``` `（含路径字符串）
   - Mermaid 图中引用的模块/文件名
   - 表格里 `path` 列、`file` 列、链接 `[xxx](path)` 等
   - 至少 1 个命中 → 把所有候选路径写进 `.ab-review/paired-code.md`（格式见下），进入正式审阅

2. **关键词匹配**（文档未引用代码时）：
   - 提取 target 文件名 stem 并去常见后缀：
     `CordicVect_analysis.md → CordicVect`、`design_note.md → design_note`
     去后缀规则：`_analysis` / `_analysis_doc` / `_note` / `_notes` / `_spec` / `_doc`
   - 在工程根（git 根 / CLAUDE.md 父）下并行搜：
     - `Glob "**/{stem}*.v"` / `Glob "**/{stem}*.sv"`
     - `Glob "**/{stem}*.bak"` / `Glob "**/{stem}*.vhdl"` / `Glob "**/{stem}*.vhd"`
     - `Grep -l "module {stem}" --include="*.v" --include="*.sv" --include="*.bak"`
     - `Grep -l "module {stem}_top"` / `Grep -l "module {stem}_core"`（常见命名变体）
   - 框架层已用 `drivers/_project.py::search_project` 跑过一轮，结果在 `.ab-review/paired-code.md` 里
   - B 角色据此补充或扩大搜索

3. **缺失告警（强制）**：以上两步全部无命中时，**立即停止审阅**，输出：

   ```
   ⚠ 配套 RTL 源未找到
   ─────────────────────────────────────
   目标文档 : <target>
   doc_class : doc-with-code
   文档内引用 : 无
   关键词匹配 : <stem> 在 .v/.sv/.bak/.vhdl/.vhd 下无命中
              <stem> 在 Grep "module <stem>" 下无命中
   已搜索范围 : project_root = <git 根 / --project-root>
   ─────────────────────────────────────
   文档内可能写了别名（如 `CORDIC_VECT` 而非 `CordicVect`），
   或 RTL 源在其他工程、用了未声明的后缀。

   选项：
     [y] 继续纯文档审阅（不核对代码，可能漏掉文档/代码漂移）
     [n] 中止本次审阅（默认）
     [p] 手动指定 RTL 源路径（一个或多个）后继续
   请选择 [y/n/p] (默认 n)：
   ```

   - 等待用户输入（同步 `--no-session-persistence` 下用 `AskUserQuestion` 或输入读取）
   - `n` → 写 `.ab-review/CODE_MISSING.md`（含上面告警内容）+ 退出，**不**写任何 `b-round-*.md`
   - `y` → 写 `.ab-review/CODE_MISSING.md`（标记"用户已确认无配套代码"）+ 继续纯文档审阅，B 报告顶部必须加：`⚠ 注：本轮未核对代码（用户已确认）`
   - `p` → 用户输入路径（空格分隔）→ 校验 `Path(p).exists()` → 写入 `.ab-review/paired-code.md` → 继续

**`.ab-review/paired-code.md` 格式**：

```markdown
# 配套 RTL 源

- target : <target>
- project_root : <git 根或 --project-root>
- max_depth : 15   # 搜索目录深度上限（[tool.mrs].precheck_max_depth 或 --precheck-max-depth）
- doc_class : doc-with-code | unknown-doc | standalone-doc
- found_by : doc-reference | keyword-match | manual | n/a
- candidates :
  - <abs-path-1>
  - <abs-path-2>
  # 或：
  - 无
  # 或（standalone-doc 时）：
  - N/A (standalone doc — 无需配套代码)
```

B 角色开始审阅时**先** `Read .ab-review/paired-code.md`（如存在）：
- `candidates` 有内容 → 据此核对代码
- `candidates: 无` + `doc_class=doc-with-code` → 已在第 3 步拿到用户选择（y/n/p）
- `candidates: N/A` + `doc_class=standalone-doc` → 直接审，无配套要求

## 对象自识别（doc / rtl 分流）

ab-review 既审文档也审代码，按 target 扩展名自动分流，两类对象用不同标准（见下）。

**判定规则**（`object_type`）：
- `.md` / `.markdown` / `.txt` → `doc`
- `.v` / `.sv` / `.vhd` / `.vhdl` → `rtl`
- 其他扩展名 → `unknown`：init 前 Read target 前 50 行试探判定（含 module/entity→rtl、## 标题→doc、都不像→问用户），详见 `REFERENCE.md §3`

**--split 模式**：object_type 由 B 端 `init --object-type <doc|rtl>` 写入 state，A 端从 state 读。默认模式由当前会话判定，不入文件。

**纠正机制**（防误判）：首轮 B 若发现 object_type 与内容不符（如 `.sv` 实为 testbench、`.md` 实为代码片段、`.sv` 是纯注释 header），在 B 意见以 **B-0** 提出"object_type 应为 X，理由..."。A 收到 B-0 后用 `_ab_state.py set-type <doc|rtl>` 改 state（默认模式则 A 直接切换标准），**后续轮按纠正后类型执行**；已产出的首轮意见不回滚。

**标准选择**：
- `object_type=doc` → 用「默认审阅标准」6 条 + 「B 额外检查清单」5 条（原文档标准）
- `object_type=rtl` → 用「代码对象替代标准」6 条 + 「B 代码专项清单」5 条（替代，非叠加）

## A/B 角色语义

- **默认：单 agent 双角色**。同一个 Claude 在回答内交替扮演 B（审阅）和 A（修改），用明确的章节标题区分（见轮次格式）。效率高，但存在"自己放过自己"风险。
- **严格模式（用户加 `--strict`）**：用 `Agent` 工具 spawn 一个**独立 subagent 充当 B**（`subagent_type: "general-purpose"`），主 agent 充当 A。B 的上下文与 A 隔离，审阅更严。每轮 B 的意见作为 Agent 返回值交给 A 执行。B 的 prompt 须明确"必须用 `Skill` 调 rtl-analyze Mode B/C 做专项检查 + 叠加本 skill 标准"——完整 prompt 模板见 `REFERENCE.md §2`。
- 两种模式都遵守：B 不得强行找茬（已说清楚处不挑刺）；A 发现 B 意见无代码支撑有权拒绝并注明原因。

## 全自动执行规则

- 所有轮次在同一次回答内完成，中途不等待用户输入。
- 每轮流程：B 展示审阅意见 → A 立即执行修改 → 进入下一轮。
- B 审阅必须指向文档**具体位置**（段落/行号/句子），说明"为什么会导致理解障碍"。
- A 修改**只能依据代码或文档已有事实**；修改前用 `Grep`/`Read` 核对代码仓库，不得臆造；无法验证的标注`【待验证】`。
- B 若发现某处已说清楚，**不得强行找茬**。
- A 若发现 B 意见无代码支撑，**有权拒绝并注明原因**。
- **终审信号**：当 B 在某轮输出字面量 `**终审通过**` 且无新增实质性意见时，本轮即终轮，自动停止。
- 最多 **3 轮**；到达 3 轮仍未通过 → 输出遗留问题清单，自动停止。

## 规模自适应策略

| 规模 | 阈值 | 策略 | 每轮 B 意见上限 | 预期轮次 |
|------|------|------|----------------|---------|
| 小 | <20KB | 全文审阅 | 8 条 | 2~3 |
| 中 | 20-80KB | 全文审阅，优先最严重 | 5 条 | 3~4 |
| 大 | >80KB | 按模块顺序逐模块审阅（按 `##` 标题切分），每轮聚焦一模块 | 5 条/模块 | 4~5 |

> **阈值按对象类型调整**：上表阈值针对 **Markdown 文档**。RTL 代码（`.v`/`.sv`）单体通常 1-15KB，>20KB 已是巨型单体，故 RTL 阈值下调一档——小 <8KB / 中 8-32KB / 大 >32KB。判断对象类型按 target 文件扩展名（`.md`→MD 阈值，`.v`/`.sv`/`.vhd`→RTL 阈值）。
>
> **RTL 大文件切分**：>32KB 的 RTL 按 `module`/`endmodule` 边界或 `// ----` 分隔注释切分，每轮聚焦一个主要功能块（FSM / datapath / CDC），而非按 `##` 标题（RTL 无此结构）。

大文档若用户未指定范围：首轮先列出文档模块清单（`##` 标题），告知将按顺序审阅，每轮聚焦一个模块直到覆盖全文或达轮次上限。建议用户后续用 `第3-5节` 精细触发。

## 默认审阅标准（object_type=doc 时适用）

以"完全没看过代码的开发者"视角，确保：
1. 每个数据的来源、去向清楚
2. 数据经过的完整处理链路清楚
3. 每个处理环节对应的算法/逻辑清楚
4. 子模块功能和数据流清楚
5. 能根据文档直观理解数学原理或算法公式
6. 代码中任何特殊处理都能找到原因

## 代码对象替代标准（object_type=rtl 时，替代上方 6 条）

以"审查综合就绪的设计模块"视角，确保：
1. 每个信号的来源与驱动完整、无悬空
2. 数据通路关键路径清晰、流水线深度合理
3. FSM 完整无死角——死状态、default 恢复、非法编码处理均就绪
4. 时钟/复位策略安全：无门控时钟、复位树正确、CDC 同步完备
5. 模块接口契约自洽：输入皆用、输出皆驱、位宽匹配、无多驱
6. 代码中特殊处理（截断、饱和、绕行）能找到原因或标注设计意图

> 这 6 条是 B 的**高视角判断框架**，与 rtl-analyze Mode B 的全量细粒度检查互补——Mode B 报具体违规，本框架保证 B 不漏"设计整体自洽"层面问题。

## B 的额外检查清单（object_type=doc 时，每轮逐项核对并标注结果）

1. **硬件资源实例化**：文档声称的每个硬件资源（SRAM/FIFO/缓存），B 必须追问"它在代码哪一层实例化的？"——层级与实际代码不符 → 标记错误。
2. **术语首次定义**：任何非行业通用的缩写/代号/专有名词（如 L1、L2、CPE）在首次出现处是否有一句话定义。无定义 → 标记缺失。
3. **信号全链路追踪**：对每个关键信号，从源头模块追踪到目的模块，确认文档描述的信号流与实际代码连线一致。不允许文档写 A→B 但代码实际 A→C→B。
4. **跨层级一致性**：若文档说某资源"在 X 模块内部"，B 需向上追溯一级代码确认 X 模块的端口声明和实例化位置支持该说法。不能仅凭端口名推断。
5. **注释与代码实现一致性**：文档可参考代码注释解析，但必须结合代码逻辑判断注释是否正确合理；注释与代码有歧义 → 必须纠正。

## B 代码专项清单（object_type=rtl 时，替代上方 5 条，互补式）

> **互补不重复**：本清单是 B 在 rtl-analyze Mode B 全量报告基础上的**人工视角复核点**，只报 Mode B 不覆盖的"设计意图/可读性/语义自洽"层面问题。Mode B 已报的（FSM 未覆盖状态、CDC 缺同步器、综合陷阱、位宽不匹配、缺复位等）**不重复报**；本清单聚焦 Mode B 的盲区——需要人工判断、设计意图层面的。

1. **位宽截断的设计意图**：截断/舍入处是否有注释说明为何丢弃高位、饱和策略——Mode B 只报"位宽不匹配"，不报"截断无理由"
2. **FSM 死状态的设计原因**：不可达状态是设计冗余还是遗漏——Mode B 报"不可达"，本条追问"为什么留它/该不该留"
3. **特殊处理的注释完备性**：绕行/打拍/特殊时序/异步路径是否有注释说明——Mode B 不查注释完备性
4. **接口契约的语义自洽**：port 命名是否反映功能、是否存在名实不符——Mode B 查语法不查语义
5. **复位策略的一致性**：同模块内复位风格是否统一、复位值是否合理——Mode B 报"缺复位"，本条追问"复位值对不对、风格统一否"

## RTL 专项审阅（叠加 rtl-analyze，不替代上述标准）

当审阅对象为硬件技术文档或 RTL 代码时，通过 `Skill` 工具调用 `rtl-analyze`。**注意角色分工**：Mode A/B/C 是 **B 角色的审阅工具**（挑刺，不改文档）；Mode E 是 **A 角色的修改工具**（当文档漂移严重或缺失时，A 用它生成/对齐文档作为修改手段）。

### B 角色审阅工具（挑刺，不改文档）

| 对象 | 调用 | rtl-analyze 模式 |
|------|------|----------------|
| 审阅**文档**（文档↔RTL 交叉核对） | `Skill(skill="rtl-analyze", args="评审文档 <path>")` | Mode C（12 类文档检查：信号名/数据宽度/参数/模块层次/时钟域/Mermaid 图/FSM/交叉引用/时序协议/死链/文档质量） |
| 审阅**RTL 代码** | `Skill(skill="rtl-analyze", args="评审代码 <path>")` | Mode B（9 大类代码评审：编码风格/锁存器/FSM/CDC/综合就绪/结构正确/PPA/DFT/领域专项） |
| 分析**RTL 代码**（辅助理解） | `Skill(skill="rtl-analyze", args="分析代码 <path>")` | Mode A（模块结构分析） |

三层标准合并为 B 的审阅意见：按 object_type 选默认标准(6条) + 专项清单(5条) + rtl-analyze Mode B/C（对应模式全类）。doc 用文档标准+硬件专项，rtl 用代码替代标准+代码专项。

### A 角色修改工具（按 object_type × 场景分流）

| object_type | B 意见类型 | A 行为 |
|-------------|-----------|--------|
| rtl | 代码 bug/缺陷 | 直接 Edit RTL，按 A 决策模板留依据（Grep/Read 核对） |
| rtl | 缺注释/文档 | 补注释或标 `【待确认】` |
| rtl | 代码与 spec 漂移 | 若项目有对应文档→`逆向文档/文档对齐`（Mode E-1/E-2）；否则直接改代码+标注 |
| doc | 文档缺失 | `Skill(skill="rtl-analyze", args="逆向文档 <rtl-path> --out <doc-path>")` → Mode E-1 |
| doc | 文档与代码漂移 | `Skill(skill="rtl-analyze", args="文档对齐 <doc-path> <rtl-path>")` → Mode E-2 |
| doc | 文档增量过时 | `Skill(skill="rtl-analyze", args="增量更新文档 <doc-path> <rtl-diff>")` → Mode E-3 |
| doc/rtl | 纯表述/排版 | 直接 Edit（不必调 Mode E） |

**A 调 Mode E 的约束**（doc 对象触发 Mode E 时）：
- Mode E 输出含"待确认清单"（设计意图类内容不编造、标 `【待确认】`）——A 须把该清单并入本轮 `a-round-N.md` 的"待验证/待确认"汇总，交 B 下轮复审，**不得静默吞掉**。
- rtl 对象时 A 主要直接 Edit 代码，仅在"代码与 spec 漂移且项目有文档"场景才触发 Mode E。
- A 用 Mode E 生成/对齐文档后，仍须按 A 决策模板逐条记录（依据=Mode E 输出 + 代码行号核对，判定=改，改动=文档段落）。
- Mode E 只处理"文档↔代码事实"类意见；纯文档表述/排版类意见 A 直接 Edit，不必调 Mode E。

> 注：`rtl-analyze` 靠 args 中的模式关键词选择模式（B 用"评审文档/评审代码/分析代码"；A 用"逆向文档/文档对齐/增量更新文档"），调用时务必带上对应关键词。

## 轮次格式

```
## 第 N 轮 — B 审阅：<文档名>
**本轮范围**: <章节/模块>
**意见数**: K条

### B-1 <标题>
- **位置**: <段落/行号>
- **问题**: <描述 + 理解障碍原因>
- **建议**: <修改方向>

（B-2 ... B-K）

---
## 第 N 轮 — A 修改（逐条可审计决策，格式见"A 决策模板"）
### A-1 对应 B-1
- **依据**: <Grep/Read 具体证据，命令+行号>
- **判定**: 改 | 拒绝 | 待验证
- **理由**: <一句话>
- **改动**: <文件:位置 old→new；拒绝/待验证留空>

### A-2 对应 B-2
...

**本轮汇总**: 改 X | 拒绝 Y | 待验证 Z

（修改完成后——B 若有新意见则进入第 N+1 轮；若输出 **终审通过** 则输出终审结论，自动结束）
```

## 终审结论格式

```
## 终审结论
- **对象**: <文档/代码路径>
- **执行轮次**: N / 3
- **结果**: 终审通过 | 达到轮次上限（遗留问题见下）
- **修改统计**: 共修改 X 处，拒绝 Y 处
- **遗留问题**（若有）:
  1. ...
  2. ...
```

## 端到端最小示例

完整范文（文档对象 + 代码对象各一例，含 B 审阅 / A 决策 / 终审结论）见 `REFERENCE.md §1`。首次使用时 Read 一次对齐格式，后续轮凭结构记忆即可。

核心结构速览：
- B 轮：`## 第 N 轮 — B 审阅：<target>` → 本轮范围/意见数 → 每条 `### B-K`（位置/问题/建议）
- A 轮：`## 第 N 轮 — A 修改` → 每条 `### A-K 对应 B-K`（依据/判定/理由/改动）+ 本轮汇总
- 终审：`## 终审结论`（对象/轮次/结果/修改统计）

## 双终端分角色模式（--split）

当 A、B 需跑在**两个终端**（不同模型 / 不同上下文，真正隔离）时，用标志文件 + 定时轮询自动乒乓，**无需人工中转**。两终端通过 `.ab-review/state.json` 协调，`/loop` 定时驱动。

核心设计：skill 在 `--split` 下是**幂等单步**——每次被唤醒只 Read state、该自己则执行一步、否则速退；靠 `/loop` 反复唤醒推进。

### 文件布局（工作目录 `.ab-review/`）

```
.ab-review/
  state.json          # 协调标志（单一真相源）
  b-round-{N}.md      # B 第 N 轮审阅意见
  a-round-{N}.md      # A 第 N 轮修改摘要
  verdict.md          # 终审结论（终审通过/遗留时写）
```

### state.json schema

```json
{
  "target": "design-note.md",
  "mode": "split",
  "round": 1,
  "turn": "b",
  "verdict": null,
  "max_rounds": 3,
  "range": null,
  "object_type": "doc",
  "updated_at": "<epoch seconds>"
}
```

- `turn`：`b`（轮到 B 审阅）/ `a`（轮到 A 修改）/ `done`（结束）。**turn 本身即互斥锁**——任一时刻只有一个角色会行动。
- `round`：当前轮次（B 第 N 轮 + A 第 N 轮为一轮）。
- `object_type`：`"doc"` | `"rtl"` —— 由 target 扩展名判定（见「对象自识别」），决定用文档标准还是代码替代标准。误判可由 B-0 提出、A 用 `set-type` 纠正。
- `verdict`：`null` / `"通过"` / `"遗留"`。非 null 即终止。

### 幂等单步协议

每次调用先 `Read .ab-review/state.json`：

**B 角色**（`--role b`）：
1. `verdict != null` → 输出 `已终止（verdict=<值>）`，退出。
2. `turn != "b"` → 输出 `等待中（turn=a, round=N）`，退出。
3. `turn == "b"`：
   - Read target 文档；round>1 时另 Read `a-round-{round-1}.md` 看 A 上轮改了什么。**若 `state["range"]` 非空，仅审阅该范围**（如 `第3-5节`、`§4`、`行 100-200`），否则全文审阅——与默认模式行为一致。
   - 执行 B 审阅：**按 `state["object_type"]` 选标准**（与 L163 一致）——`doc` → 6 默认标准 + 5 硬件专项；`rtl` → 6 代码替代标准 + 5 代码专项；再叠加 rtl-analyze Mode C（doc）/ Mode B（rtl）。不得对 rtl 对象套用文档标准。
   - Write `b-round-{round}.md`（按轮次格式）。
   - **若无实质意见**（本轮 B 认为已清楚）→ Write `verdict.md`（终审通过），原子更新 state：`turn=done, verdict=通过`。
   - **否则**原子更新 state：`turn=a`（round 不变，等 A 改）。
4. 退出，等下次轮询。

**A 角色**（`--role a`）：
1. `verdict != null` → 输出 `已终止`，退出。
2. `turn != "a"` → 输出 `等待中（turn=b, round=N）`，退出。
3. `turn == "a"`：
   - Read `b-round-{round}.md`。
   - **逐条决策**：对 B 的每条意见（B-1..B-K），按"A 决策模板"输出 `{依据/判定/理由}`——改前必须 `Grep`/`Read` 核对，**无依据不得改**。
   - 执行修改（in-place Edit target，只能依据已有事实，无法验证标`【待验证】`）。**文档↔代码事实类意见**（漂移/缺失）可调 `rtl-analyze` Mode E 生成/对齐文档（见"RTL 专项审阅·A 角色修改工具"），Mode E 的"待确认清单"须并入本轮 `a-round-N.md` 交 B 复审。
   - Write `a-round-{round}.md`，内容=每条意见的决策记录（不是笼统摘要，见决策模板规范）。
   - 若 `round+1 > max_rounds` → Write `verdict.md`（遗留问题清单），原子更新 state：`turn=done, verdict=遗留`。
   - 否则原子更新 state：`turn=b, round=round+1`。
4. 退出，等下次轮询。

### A 决策模板（可审计，强制逐条核对）

A 收到 B 意见后，**每一条**都必须走"依据→判定→理由"三步，**不得笼统接受整批意见**。目的是让 A 是否真核实变得可检查——若某条"依据"为空或泛泛，说明 A 跳过了核对，B 下轮或人工可据此质疑。

`a-round-{N}.md` 必须按以下结构，一条一块：

```markdown
## A 第 {N} 轮决策：<target>
**对应 B 意见**: b-round-{N}.md（{K} 条）

### A-1 对应 B-1 <B-1 标题>
- **依据**: <必须填，Grep/Read 的具体证据>
  - 例：`Grep "rx_data" rtl/top.sv` → 命中 line 87,102，确认 rx_data 经 rx_fifo
  - 例：`Read docs/spec.md §3.2` → 无此说法，B 意见无文档支撑
- **判定**: 改 | 拒绝 | 待验证
- **理由**: <一句话>
- **改动**（判定=改时必填）: <文件:位置，old→new 摘要；拒绝/待验证则留空>

### A-2 对应 B-2 ...
...

## 本轮汇总
- 改: X 条 | 拒绝: Y 条 | 待验证: Z 条
- 拒绝/待验证清单（供 B 下轮复审）:
  - A-2 拒绝: <一句话原因>
  - A-5 待验证: <无法核实什么>
```

**判定规则**（硬约束）：
- **判定=改**：`依据`必须是非空的具体证据（命令+行号/文件段落）。依据为空 → 不许改。
- **判定=拒绝**：B 意见无代码/文档支撑，或会破坏正确性。`理由`必须指出 B 错在哪。
- **判定=待验证**：有道理但当前无法核实（缺代码访问/需运行验证）。标`【待验证】`，target 文档对应处也加上该标记，B 下轮重点复审。

**禁止行为**：
- 禁止"依据: 经核对无误"这类无信息量填充——必须有可复现的命令或定位。
- 禁止批量接受（"采纳 B-1~B-5 全部意见"）——必须逐条。
- 禁止只改不记——即便判定=改，也要留依据链，否则等同跳过核对。

> 这套模板让 A 的判断过程**可审计**：B 下一轮读 `a-round-{N}.md` 时能看到 A 对自己每条意见的依据与判定，对"拒绝"可反驳、对"待验证"可补证。人工抽查时，`依据`字段空泛与否即 A 是否真核对的直接证据。

### 对话历史管理（防多轮遗忘，硬约束）

多轮审阅遗忘的根因是 b-round/a-round/rtl-analyze 报告在对话历史里累积。每轮严格遵守：

1. **B 每轮只 Read**：本轮 target 范围（按 `state["range"]`）+ 上一轮 `a-round-{round-1}.md`（看 A 上轮改了什么）。**禁止** Read 全部历史 round 文件。
2. **A 每轮只 Read**：本轮 `b-round-{round}.md` + 本轮要改的 target 段落。**禁止** Read 全部历史 round 文件。
3. **需要全历史时**：用 state.json 的 round 计数定位落盘的 `b-round-N.md`/`a-round-N.md`，**按需 Read 特定轮次**，不全量载入。
4. **rtl-analyze 报告不进对话**：B 调 Mode B/C 拿到的报告，只把"本轮要提的意见"摘入 `b-round-N.md`，整份 Mode B 报告落盘到 `.ab-review/modeB-round-N.md` 备查，**对话里只留摘要**。**B 产出 `b-round-N.md` 前必须先 Write `modeB-round-N.md`**（若本轮调了 Mode B/C），否则等同违反本条——防止报告只活在对话里、未落盘即丢失。
5. **默认模式（非 split）同样适用**：每轮只回顾上一轮，不把所有历史轮次留在上下文。

每轮对话只承载"上一轮 + 本轮"，历史轮次落盘按需查，对话历史不再线性增长。

### 原子写与 state 契约（用 `_ab_state.py`，禁止手写 state）

state.json 的读-改-写**必须**通过 `skills/ab-review/scripts/_ab_state.py` 完成。它内部用 `flock` 持锁 + `os.replace` 原子覆盖，是 state 的唯一写入者。**禁止** LLM 直接 Edit/Write state.json——会绕过锁、破坏原子性。

脚本路径（两种等价取法）：
- 绝对：`~/.claude/skills/ab-review/scripts/_ab_state.py`
- 相对：从工作目录 `python3 ~/.claude/skills/ab-review/scripts/_ab_state.py <cmd> ...`

子命令（每次唤醒按角色调用）：

| 阶段 | 谁调 | 命令 | 行为 |
|------|------|------|------|
| 启动 | B 端 `--init` | `init <target> --object-type <doc\|rtl> --range R --max-rounds N` | 建 state（turn=b,round=1,object_type 写入）；已存在则不动 |
| 探活 | 每次唤醒先调 | `claim <role>` | 该自己→`{"act":true,...}`；否则→`{"act":false,"turn":...}`（速退）；已 done→`{"done":true,"verdict":...}` |
| B 改完 | B 角色 | `handoff b` | turn=a（round 不变）；若 B 无意见改用 `finish 通过` |
| A 改完 | A 角色 | `handoff a` | turn=b,round+1；超 max_rounds→verdict=遗留,turn=done |
| B 终审 | B 角色 | `finish 通过` | turn=done,verdict=通过 |
| 纠正类型 | A 角色 | `set-type <doc\|rtl>` | 改 state.object_type（B-0 提出误判后 A 纠正） |
| 中止 | 人工 | `reset` | 删 state+lock |

`claim` 是**只读探活**（不加锁写），`handoff`/`finish` 是**加锁推进**。Bash 典型唤醒序列（claim→判 act→执行/速退）见 `REFERENCE.md §4`。

### 启动与轮询命令

**B 端首次启动**（建 state + 跑第 1 轮 B）：
```
/ab-review design-note.md --split --role b --init              # object_type 由 target 扩展名自动判定
/ab-review rtl/top.sv --split --role b --init                  # .sv → object_type=rtl 自动写入 state
```
`--init` 创建 `.ab-review/state.json`（turn=b, round=1, max_rounds=3, **object_type 由 target 扩展名判定写入**）并立即执行第 1 轮 B。

> **`--init` 只跑首轮，不是持续运行的**。首轮 B 执行完毕后 handoff 到 `turn=a` 即退出，**不会自动回来接后续轮次**。因此 `--init` 执行完毕后必须**立即在同一终端挂 `/loop`**，否则 B 终端断开后 A handoff 回 `turn=b` 无人接棒，流程卡住。`/loop` 命令见下方轮询说明。

> **init 前必须先判定 object_type**：按「对象自识别」规则（扩展名 → doc/rtl，unknown 读前 50 行试探），判定后通过 `init --object-type <doc|rtl>` 传入 state。若不传，object_type=null，两端每次唤醒都要重新从 target 推断——**务必传**。误判可由首轮 B-0 提出、A 用 `set-type` 纠正。

**A 端启动**（只轮询，不建 state）：
```
/ab-review design-note.md --split --role a
```

**两端各自挂定时轮询**（每 2~3 分钟唤醒，幂等检查 state；不该自己时速退不空耗）：
```
/loop 2m /ab-review design-note.md --split --role b
/loop 2m /ab-review design-note.md --split --role a
```

> 启动顺序：B 端先 `--init` 跑完第 1 轮（state 置 turn=a）→ A 端再挂 `/loop`。否则 A 端首次轮询会看到 turn=b 而"等待中"——这是正常的，下个轮询周期会接到活。

### 终止

- **B 无实质意见** → verdict=通过，turn=done。两端下次轮询见 `verdict != null` 即输出终止并退出；`/loop` 可人工停或靠其 7 天自动过期。
- **round 超 max_rounds** → A 端置 verdict=遗留，turn=done，输出遗留清单。
- **人工中止**：删 `.ab-review/state.json`，或直接置 `turn=done`。
- **卡住检测**（可选）：`claim` 返回的 `stale_seconds` 字段表示距上次 turn 推进的秒数。若 `stale_seconds > 1800`（30 分钟）且 `act=false`（不是自己回合也没 done），输出告警（可能对端终端没开 / `/loop` 没挂）。无需手算 `updated_at` 差值——`_ab_state.py` 的 `claim` 已内置该字段。

### --split 与默认模式的关系

| | 默认模式（无 --split） | --split 模式 |
|---|---|---|
| 进程 | 单进程内 A/B 自闭环 | 两进程，各跑一个角色 |
| 推进 | 一次回答跑满 3 轮 | 每次唤醒只走一步，`/loop` 驱动 |
| 协调 | 无需 | `.ab-review/state.json` 标志文件 |
| 模型隔离 | 无（同一模型演两角） | 有（A/B 可用不同模型） |

检查清单、轮次格式、终审信号（`**终审通过**`）、3 轮上限——两种模式**完全一致**，仅执行载体不同。

## 失败模式与避免

- **A 臆造**：未 Grep/Read 核对就改 → 必须先验证；无法验证标`【待验证】`交还用户。
- **B 强行找茬**：已清楚处硬挑 → B 每条意见必须说明"理解障碍原因"，说不出的不提。
- **无限循环**：B 永不通过 → 硬上限 3 轮，到顶输出遗留清单停止。
- **路径误改**：in-place 改错文件 → 修改前必 Read 全文确认路径；RTL 改动前确认 git 状态。
- **rtl-analyze 模式调错**：审文档却用 Mode B → 按"对象→模式"表严格对应，args 带对关键词。

## 维护说明

脚本清单、回归自测命令、脚本调用约定、改 skill 正文的回归方法见 `REFERENCE.md §5`。

关键约束（执行时必守）：`--split` 所有 state 读写走 `_ab_state.py`，**禁止** LLM 直接 Edit/Write `.ab-review/state.json`（绕过 flock+os.replace 破坏原子性）。改 `_ab_state.py` 后必跑 `_ab_split_selftest.py` 回归。