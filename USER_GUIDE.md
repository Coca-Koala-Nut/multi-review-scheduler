# multi-review-scheduler 用户手册

> 写给第一次使用这个工具的人。每一步都告诉你按什么、会出现什么。

> **须知**：文档里代码块标着 `bash` 只是 markdown 的语法高亮（让代码有颜色），**不要求你必须用 bash**。Windows 自带的 PowerShell、cmd，Mac 的 zsh，Linux 的 fish 等终端都能跑同样的命令。如果 `python3` 不存在，换 `python` 或 `py` 试试。

## 0. 拿到工程后：5 步开始用

> 假设你刚拿到这个工程（zip / git clone / 内网分享），电脑上**什么都没装**。按下面 5 步走完就能跑。

### 第 1 步：打开终端

- **Windows**：按 `Win+R` → 输入 `cmd` → 回车；或装 Windows Terminal；Win11 系统鼠标右击开始菜单，点击"终端"按钮
- **Mac**：按 `Cmd+空格` → 输入 `Terminal` → 回车
- **Linux**：直接打开"终端"应用

### 第 2 步：进入工程目录

```bash
cd 路径/到/multi_review_scheduler
```

例：

```bash
# Windows
cd C:\Users\username\projects\multi_review_scheduler

# Mac / Linux
cd ~/projects/multi_review_scheduler
```

> 不会用 `cd`？把工程文件夹直接拖到终端窗口里，路径会自动填上。

### 第 3 步：装齐依赖（推荐用 bootstrap）

**方式 A：一键启动器（推荐新用户）**

```bash
python3 mrs-bootstrap.py
```

它会自动：检测 Python 版本 → 检测 pip → `pip install --user multi-review-scheduler[full]` → 启动 TUI。

> 看到一大段 pip install 输出是正常的，让它跑完。**首次需要 1-3 分钟**（取决于网速）。
>
> **报错说"python3 不存在"？** 改用 `python` 或 `py`：
> ```bash
> python mrs-bootstrap.py
> ```

**方式 B：手动装（已熟悉 pip）**

```bash
pip install multi-review-scheduler[full]
```

`[full]` = ab-review skill + rtl-analyze skill + TUI（textual + tomlkit）全装上。

只想要 TUI 不想要某个 skill：

```bash
pip install multi-review-scheduler[ab-review,tui]   # 只装 ab-review
pip install multi-review-scheduler[rtl,tui]         # 只装 rtl-analyze
pip install multi-review-scheduler[tui]              # 只装 TUI（不带任何 skill）
```

PEP 668 系统 Python（Debian / Ubuntu）需加 `--break-system-packages`，或先 `python3 -m venv .venv && source .venv/bin/activate`。

### 第 4 步：启动 TUI

```bash
multi-review-scheduler --ui
```

屏幕变成这样（简化）：

```
┌──────────────────────────────────────────────────────────────┐
│ [Q] Save & Quit   [Esc] Quit (no save)   [Tab] 切字段        │ ← 顶栏：快捷键
├──────────────────────────────────────────────────────────────┤
│ 目标文件 *                       [必填，如 CordicVect_analysis.md]
│ 默认 workflow                    [ab-review ▼]
│ B 角色 settings.json             [~/.claude/settings-db-kimi.json]
│ A 角色 settings.json             [~/.claude/settings-ds.json]
│ 最大轮次                         [3]
│ B 角色额外提示                   [如 '重点看时序']
│ A 角色额外提示
│ 项目根（搜索范围）               [留空=自动]
│ 文档分类                         [auto ▼]
│ 单步超时（分）                   [30]
│ 日志路径                         [.ab-review/run.log]
│ pre-check 搜索深度               [15]
├──────────────────────────────────────────────────────────────┤
│ loaded: (new)                                                 │ ← 底栏：状态
└──────────────────────────────────────────────────────────────┘
```

每个格子是一个**字段**，代表一项配置。

### 第 5 步：填配置 + 保存 + 跑

1. **Tab** 跳到下一格，**Shift+Tab** 跳回
2. 至少填第一格"目标文件"（带 `*` 必填），其他可保持默认
3. 按 **Q** 保存并退出 TUI
4. 回到命令行，跑：

```bash
multi-review-scheduler
```

工具自动读 `[tool.mrs]` 配置，按你填的目标跑。

### 跑过一次后

```bash
cd 路径/到/multi_review_scheduler      # 第 2 步
multi-review-scheduler                      # 用上次保存的配置直接跑
```

要改配置再开 TUI：

```bash
multi-review-scheduler --ui
```

---

## TUI 是什么

TUI 是"终端里的图形界面"——你打开它，会看到一个菜单，可以填表、保存、退出。
跟微信、Excel 那种"点图标"的 GUI 不一样，它在黑色窗口里运行，用**键盘**操作。

---

## 在 TUI 里操作

### 移动光标

- **Tab**：跳到下一个字段
- **Shift+Tab**：跳回上一个字段
- **方向键 ↑↓**：在 Select（下拉框）里切换选项

### 改字段值

- 格子是输入框（带光标闪烁）：直接**打字**就能改，按 **退格键**（Backspace）删除
- 格子是下拉框（右边有 `▼` 符号）：按 **回车** 或 **空格** 弹出选项，再用 **↑↓** 选

### 必填字段

带 `*` 星的字段是**必填**（比如第一个"目标文件"）。
留空按 Q 保存会失败，底栏会提示 `⚠ default_target 不能为空；请填写目标文件路径`。

### 保存与退出

| 快捷键 | 作用 |
|---|---|
| **Q** | 保存配置到 `pyproject.toml [tool.mrs]` 并退出 TUI |
| **Esc** | **不保存**直接退出（之前填的丢掉） |

> 大小写都行：按 `q` 或 `Q` 都生效。

保存成功后底栏会显示 `saved: <路径> → 退出`。**TUI 不自动跑工作流**——回到命令行自己敲 `multi-review-scheduler` 跑。

---

## pre-check：自动找配套 RTL 源

文档类目标（`_analysis.md` / `_design.md` / `_spec.md` 等）跑前会自动搜配套 RTL 源，结果写到 `.ab-review/paired-code.md`，并把候选路径摘要注入 B/A 角色 prompt。

### 找不到 RTL 源怎么办

如果目标判定为 `doc-with-code`（文档应配套代码）但工程根下没找到，**脚本层会阻塞**：

```
[ab-review] CordicVect_analysis.md 是 doc-with-code 但 /home/xxx 下未找到 RTL 源（max_depth=15）。
  [y] 继续审（无 RTL 上下文）  [n] 中止  [p] 打印搜索结果详情
>
```

同时会写 `.ab-review/CODE_MISSING.md`（含 target / project_root / max_depth / stems / 排查建议）。

**选项**：

- **y**：继续审（B/A 角色拿不到 RTL 上下文，可能漏代码核对）
- **n**：中止，去修正 target / project_root / doc-class 后重跑
- **p**：打印搜索详情（target / project_root / stems / max_depth）

非 TTY 环境（CI / 脚本）：默认继续，stderr 一行警告，不阻塞。

强制跳过阻塞（Power user）：`--no-precheck-block` 或 `no_precheck_block = true`。

### pre-check 搜索深度

SoC IP 经常深达 9-12 层（`IPs/HW/<proj>/<block>/<sub>/<subsub>/verilog/rtl/`）。默认 `max_depth=15` 够用。

要更深/更浅：

```bash
multi-review-scheduler --precheck-max-depth 25     # 临时
```

或在 `pyproject.toml [tool.mrs]` 写：

```toml
precheck_max_depth = 25
```

---

## 常用命令速查

```bash
# 装
pip install multi-review-scheduler[full]

# 跑（用 [tool.mrs] 配置）
multi-review-scheduler

# 跑（覆盖目标）
multi-review-scheduler --target 其他文件.md

# 跑（覆盖多个字段）
multi-review-scheduler --max-rounds 5 --timeout 60 --settings-b /abs/path/settings.json

# 只装 skill 不跑（首次 / 升级）
multi-review-scheduler --install-only

# 列可用 workflow
multi-review-scheduler --list-workflows

# 单次 skill（不跑 A/B 循环）
multi-review-scheduler --workflow rtl-analyze --target rtl/top.sv

# TUI（编辑 [tool.mrs]）
multi-review-scheduler --ui

# 跳过配置（只用 CLI 参数）
multi-review-scheduler --no-config --target X

# 重置 ab-review state
multi-review-scheduler --reset

# dry-run（只打印将执行的命令，不真跑）
multi-review-scheduler --dry-run
```

---

## 配置文件在哪

TUI 保存的默认路径：**当前工作目录**下的 `pyproject.toml` 的 `[tool.mrs]` 段。

例如在 `/home/me/my-project/` 跑 TUI，就存到 `/home/me/my-project/pyproject.toml`。
下次再跑 TUI，会自动读这份配置——不用重新填。

想用现成示例起手：`cp mrs.example.toml pyproject.toml`，把 `default_target` 填上即可。详见 `mrs.example.toml` 注释。

---

## 常见问题

### Q1：按 Q 没反应？

可能字段没填完。检查底栏有没有红字提示，按提示补字段再按 Q。

### Q2：保存的文件在哪？

当前工作目录的 `pyproject.toml [tool.mrs]` 段。

### Q3：TUI 保存后怎么跑？

回到命令行直接敲：

```bash
multi-review-scheduler
```

它会自动用 `[tool.mrs]` 里的配置。

### Q4：怎么用绝对路径覆盖某一项？

```bash
multi-review-scheduler --settings-b /home/你的用户名/.claude/settings-b.json
```

CLI 参数优先级 > 配置文件 > 内置默认。

### Q5：怎么强制不读配置？

```bash
multi-review-scheduler --no-config --target <文件> ...
```

### Q6：想重置成默认配置？

编辑 `pyproject.toml` 删 `[tool.mrs]` 整段；或在 TUI 里把所有字段改回空/默认，再按 Q 保存。

### Q7：启动立刻打"工作流结束"、但啥也没跑？

`.ab-review/state.json` 里残留了旧 state（可能上次没跑完）。
新版本会自动检测并 reset 一次（终端会打 `[ab-review] 旧 state 来自 XXX... → 自动 reset`）。

> **边界条件**：如果带了 `--resume`，自动 reset **不会**触发（你显式要续跑就别覆盖）。要强行清干净：

```bash
multi-review-scheduler --reset
```

### Q8：claude 报 "Settings file not found: ~/.claude/xxx.json"（但文件实际存在）？

新版本会在 mrs 层自动 `expanduser()`，正常情况 `~/.claude/...` 直接写就行。
如果还遇到，写**绝对路径**最稳：

```bash
multi-review-scheduler --settings-b /home/你的用户名/.claude/settings-b.json
```

### Q9：终端里中文显示乱码？

换 Windows Terminal / iTerm / 现代 Linux 终端。Windows 自带的旧 cmd 渲染不好。

### Q10：TUI 启动报"缺 TUI 依赖"？

TUI 不自动 pip install（避免污染你的 Python 环境）。手动装：

```bash
pip install multi-review-scheduler[tui]
```

或在 venv / `--break-system-packages` 下重装主包带 `[tui]` extra。

---

## 一张图速查

```
打开 TUI    multi-review-scheduler --ui
移动        Tab / Shift+Tab / ↑↓
下拉        回车 / 空格 → ↑↓ 选
保存退出    Q
不保存退出  Esc
跑一次      multi-review-scheduler
覆盖单次    multi-review-scheduler --<字段> <值>
跳过配置    multi-review-scheduler --no-config
```

---

## 出错了怎么办

| 现象 | 怎么办 |
|---|---|
| `缺 TUI 依赖: textual, tomlkit` | 手动 `pip install multi-review-scheduler[tui]` |
| `default_target 不能为空` | TUI 里第一格"目标文件"必须填 |
| `pip install 失败` | 检查网络；或 `pip install --user multi-review-scheduler[full]` |
| `Settings file not found: ~/.claude/xxx.json` | 写绝对路径，或确认 `~/.claude/xxx.json` 存在 |
| `CordicVect.md 是 doc-with-code 但 X 下未找到 RTL 源` | pre-check 阻塞，y 继续 / n 中止 / p 看详情；或 `--no-precheck-block` 跳过 |
| 想强制取消 | `Ctrl+C`（runner 会安全中断，state 保留可续跑） |