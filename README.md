# multi-review-scheduler

Skill 工作流调度框架，基于 Claude Code CLI。

把 `ab-review` / `rtl-analyze` 等 skill 拆为独立 PyPI 包，通过
`importlib.metadata.entry_points` 自发现；runner 调 `claude -p` 流式执行。

## 安装

主包 + skill 包独立装：

```bash
# 1. 主包（必需）
pip install multi-review-scheduler

# 2. skill 包（按需）
pip install multi-review-scheduler[ab-review]   # 只装 ab-review
pip install multi-review-scheduler[rtl]         # 只装 rtl-analyze
pip install multi-review-scheduler[all]         # 两个都装
pip install multi-review-scheduler[tui]         # TUI 配置界面（textual + tomlkit）
pip install multi-review-scheduler[full]        # all + tui

# 本地开发（editable）：
pip install -e .
pip install -e ./skills/ab-review
pip install -e ./skills/rtl-analyze
```

**找不到包时 fallback**：

主包会用 `importlib.metadata.entry_points` 自发现 skill；如果 skill 包未装，
runner 会给友好提示，例如：

```
[mrs] 未找到 packaged skill: mrs-skill-ab-review
请先 `pip install multi-review-scheduler[ab-review]`
或本地开发模式 `pip install -e ./skills/ab-review`
```

PEP 668 系统 Python 需加 `--break-system-packages`，或先 `python3 -m venv .venv`。

## 使用

```bash
# A/B 多轮审阅（默认 workflow）
multi-review-scheduler \
    --target CordicVect_analysis.md \
    --settings-b ~/.claude/settings-db-kimi.json \
    --settings-a ~/.claude/settings-ds.json \
    --max-rounds 3

# 单次 skill（rtl-analyze / cpp-analyze / 任意 packaged skill）
multi-review-scheduler --workflow rtl-analyze --target rtl/top.sv \
    --settings ~/.claude/settings-ds.json

# 仅安装 skill 后退出（幂等；用 sha256 比对 SKILL.md 决定 installed/skipped/updated）
multi-review-scheduler --install-only

# TUI 配置界面（写入 pyproject.toml [tool.mrs]）
multi-review-scheduler --ui

# 列出所有可用 workflow
multi-review-scheduler --list-workflows
```

也可 `python3 -m multi_review_scheduler` 调用。

## 配置（[tool.mrs]）

优先级：CLI 显式 > `[tool.mrs]` > 内置默认。

首次配置推荐用 TUI（`multi-review-scheduler --ui`）。手动配置：

1. 复制示例：`cp mrs.example.toml pyproject.toml`（或追加到现有 pyproject.toml 末尾）
2. 编辑 `[tool.mrs]` 段：`default_target` / `default_workflow` / `settings_b/a` /
   `max_rounds` / `b_extra` / `a_extra` / `project_root` / `doc_class` /
   `timeout_min` / `log_path` / `precheck_max_depth`
3. 跑 `multi-review-scheduler --target X` 自动读

字段含义见 `mrs.example.toml` 注释。

CLI 显式覆盖任何字段：`--max-rounds 5 --timeout 60 --project-root ~/other/proj`
等等。

## TUI

```bash
# 装 TUI 依赖（一次性）
pip install multi-review-scheduler[tui]

# 启动 TUI
multi-review-scheduler --ui
```

- 编辑 11 个 `[tool.mrs]` 字段，Tab 切换
- `Q` 保存并退出（写 pyproject.toml）
- `Esc` 退出（不保存）
- 缺包时 stderr 一行提示 + exit 2，**不自动 pip install**（避免污染环境）

保存后自己跑 `multi-review-scheduler --target X` 即可。

## 当前目录结构

```
multi_review_scheduler/
├── pyproject.toml             # 主包 multi-review-scheduler（不含 [tool.mrs]）
├── mrs.example.toml           # [tool.mrs] 配置示例
├── .gitignore                 # 防回退（__pycache__ / .ab-review / dist / ...）
├── .githooks/pre-commit       # 阻断 [tool.mrs] 误提交
├── multi_review_scheduler/    # 主包代码（CLI + TUI + 配置 IO）
│   ├── __init__.py            # CLI 入口（main）
│   ├── __main__.py            # python3 -m 入口
│   ├── config_io.py           # TOML 读写（保留其他 section / 注释）
│   ├── skills_runtime.py      # ★ entry_points 发现 + install
│   └── tui.py                 # textual 配置界面
├── drivers/                   # 与 multi_review_scheduler/ 平级（工程根下）
│   ├── base.py                # WorkflowDriver / Step 抽象
│   ├── ab_review.py           # A/B 多轮审阅驱动
│   ├── single_skill.py        # 单次 skill 驱动
│   └── _project.py            # 工程根识别 + 受控搜索 + 关键词抽取
├── engine/                    # 与 multi_review_scheduler/ 平级（工程根下）
│   └── runner.py              # 通用主循环（claude -p 调度 + 心跳 + 超时）
├── skills/                    # skill 子包（独立 wheel，通过 entry_points 注册）
│   ├── ab-review/             # mrs-skill-ab-review
│   └── rtl-analyze/           # mrs-skill-rtl-analyze
```

## 扩展新 workflow / skill

**新 skill（无状态机）**：
1. 在 `skills/<name>/` 建独立 PyPI 包，含 SKILL.md + scripts
2. `pip install -e ./skills/<name>` 装上
3. 直接用：`multi-review-scheduler --workflow <name> --target X`（自动走 `single_skill` driver）

**新 workflow（带状态机）**：
1. 继承 `WorkflowDriver` 在 `drivers/<name>.py`
2. 在 `multi_review_scheduler/__init__.py::_resolve_workflow` 注册
3. `multi-review-scheduler --workflow <name> --target X`

## 环境变量

- `CLAUDE_CMD` — Claude Code CLI 命令（默认 `claude`）
- `MRS_TIMEOUT_MIN` — 单步超时分钟数（默认 30）
- `MRS_PERMISSION_MODE` — claude `--permission-mode`（默认 `auto`）
- `MRS_HEARTBEAT_SEC` — 心跳打印间隔秒数（默认 30）
- `MRS_SETTINGS_B` / `MRS_SETTINGS_A` — 默认 settings 路径
- `MRS_STATE_SCRIPT` — ab-review 状态脚本路径