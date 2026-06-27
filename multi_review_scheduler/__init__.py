#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_review_scheduler —— skill 工作流调度框架 CLI 入口。

支持的 workflow：
- ``ab-review``（默认）：A/B 多轮审阅循环。
- 其它 workflow 由 ``--workflow <name>`` 选择，详见 ``--list-workflows``。

把 ``ab-review`` skill 打包进 ``skills/`` 后会自动安装到
``~/.claude/skills/``；不依赖用户手动部署。

示例：
    # A/B 审阅（默认 workflow）
    multi-review-scheduler \\
        --target CordicVect_analysis.md \\
        --settings-b ~/.claude/settings-db-kimi.json \\
        --settings-a ~/.claude/settings-ds.json \\
        --max-rounds 3

    # 单次调用 rtl-analyze
    multi-review-scheduler \\
        --workflow rtl-analyze --target rtl/top.sv \\
        --settings ~/.claude/settings-ds.json

    # 仅安装 skill 后退出
    multi-review-scheduler --install-only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# 让包既可 ``python3 -m multi_review_scheduler`` 跑，也可 import。
_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from drivers.ab_review import ABReviewDriver            # noqa: E402
from drivers.base import WorkflowDriver                 # noqa: E402
from drivers.single_skill import SingleSkillDriver      # noqa: E402
from engine.runner import RunnerConfig, run             # noqa: E402
from .skills_runtime import list_packaged_skills        # noqa: E402


CLAUDE_CMD = os.environ.get("CLAUDE_CMD", "claude")
DEFAULT_TIMEOUT = int(os.environ.get("MRS_TIMEOUT_MIN", "30"))
DEFAULT_PERMISSION = os.environ.get("MRS_PERMISSION_MODE", "auto")
DEFAULT_HEARTBEAT = int(os.environ.get("MRS_HEARTBEAT_SEC", "30"))


# ---------------------- workflow 注册表 ----------------------
def _ab_review_driver() -> WorkflowDriver:
    return ABReviewDriver()


def _single_skill_driver(workflow: str) -> WorkflowDriver:
    return SingleSkillDriver(workflow=workflow)


# 简单工作流注册：name -> (driver_factory, default_config)
WORKFLOWS: dict[str, dict] = {
    "ab-review": {
        "factory": _ab_review_driver,
        "help": "A/B 多轮审阅循环（B 审阅 → A 修改 → … → B 终审）",
        "config_keys": {
            "target", "max_rounds", "object_type", "range",
            "model_b", "model_a",
            "settings_b", "settings_a",
            "b_extra", "a_extra",
            "reset", "resume",
            "state_file", "state_script",
        },
    },
}


def _resolve_workflow(name: str) -> WorkflowDriver:
    """根据 workflow 名返回对应 driver。"""
    if name == "ab-review":
        return _ab_review_driver()
    # 其它走 single_skill（rtl-analyze / cpp-analyze / python-analyze）
    return SingleSkillDriver(workflow=name)


# ---------------------- CLI ----------------------
def _print_workflows(out=sys.stdout) -> None:
    out.write("可用 workflow：\n")
    for n, info in WORKFLOWS.items():
        out.write(f"  - {n}: {info['help']}\n")
    packaged = list_packaged_skills()
    single_skill = [s for s in packaged if s not in WORKFLOWS]
    if single_skill:
        out.write("单次 skill（按 packaged skill 自动注册）：\n")
        for s in single_skill:
            out.write(f"  - {s}: 调用 /{s} <target>\n")


def _read_model_from_settings(settings_path: Path | None) -> str | None:
    if settings_path is None:
        return None
    p = Path(settings_path).expanduser()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    model = data.get("model")
    if model:
        return str(model).strip()
    env = data.get("env") or {}
    model = env.get("ANTHROPIC_MODEL")
    return str(model).strip() if model else None


def _resolve_model(role: str, model_arg, settings_arg, *, out=sys.stderr) -> str:
    if model_arg:
        return model_arg.strip()
    inferred = _read_model_from_settings(settings_arg)
    if inferred:
        print(f"[{role}] 未指定模型，从 settings 推断为: {inferred}", file=out)
        return inferred
    print(
        f"错误: [{role}] 既未指定模型，也未在 settings 中找到 'model' 或 'env.ANTHROPIC_MODEL'。",
        file=out,
    )
    sys.exit(1)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="multi_review_scheduler",
        description="基于 Claude Code CLI 的 skill 工作流调度框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="环境变量：CLAUDE_CMD / MRS_TIMEOUT_MIN / MRS_PERMISSION_MODE / "
               "MRS_HEARTBEAT_SEC / MRS_SETTINGS_B / MRS_SETTINGS_A / MRS_STATE_SCRIPT",
    )
    ap.add_argument("--workflow", default="ab-review",
                    help="工作流名（默认: ab-review；亦可填 packaged skill 名）")
    ap.add_argument("--target", help="审阅/分析目标路径")
    ap.add_argument("--list-workflows", action="store_true",
                    help="列出所有可用 workflow 后退出")

    # A/B 专属参数
    ap.add_argument("--model-b", help="B 角色模型（未指定时从 --settings-b 推断）")
    ap.add_argument("--model-a", help="A 角色模型（未指定时从 --settings-a 推断）")
    ap.add_argument("--max-rounds", type=int, default=None,
                    help="最大轮次（未指定时用 [tool.mrs].max_rounds，回退 3）")
    ap.add_argument("--object-type", choices=["doc", "rtl"], help="强制指定对象类型")
    ap.add_argument("--range", help="审阅范围，如 '第3-5节' / '行 100-200'")
    ap.add_argument("--b-extra", help="B 角色额外说明，拼在 /ab-review 后")
    ap.add_argument("--a-extra", help="A 角色额外说明，拼在 /ab-review 后")
    ap.add_argument("--settings-b", default=os.environ.get("MRS_SETTINGS_B"),
                    help="B 角色 settings.json 路径")
    ap.add_argument("--settings-a", default=os.environ.get("MRS_SETTINGS_A"),
                    help="A 角色 settings.json 路径")

    # 通用
    ap.add_argument("--timeout", type=int, default=None,
                    help="单步超时分钟数（未指定时用 [tool.mrs].timeout_min，回退环境变量 / 30）")
    ap.add_argument("--heartbeat", type=int, default=None,
                    help="心跳打印间隔秒数（未指定时用 [tool.mrs].heartbeat_sec，回退环境变量 MRS_HEARTBEAT_SEC / 30）")
    ap.add_argument("--permission-mode", default=None,
                    help="claude --permission-mode（未指定时用 [tool.mrs].permission_mode，回退 MRS_PERMISSION_MODE / auto）")
    ap.add_argument("--claude-cmd", default=CLAUDE_CMD, help="覆盖 Claude CLI 命令")
    ap.add_argument("--log-path", default=None,
                    help="日志落盘路径（未指定时用 [tool.mrs].log_path，回退 .ab-review/run.log）")
    ap.add_argument("--settings", help="单次 skill 模式下的 --settings")
    ap.add_argument("--model", help="单次 skill 模式下的 --model（未指定时从 --settings 推断）")
    ap.add_argument("--project-root", help="显式指定工程根；用于 Glob/Grep 搜索范围（默认自动识别 git/CLAUDE.md 父目录）")
    ap.add_argument("--doc-class", choices=["auto", "with-code", "standalone"],
                    help="强制覆盖文档分类（auto = 按文件名自动）")

    # 流程控制
    ap.add_argument("--reset", action="store_true", help="A/B：重置 state.json 后再开始")
    ap.add_argument("--resume", action="store_true", help="A/B：发现已有 state 时直接续跑")
    ap.add_argument("--no-precheck-block", action="store_true",
                    help="doc-with-code 找不到 RTL 源时跳过脚本层阻塞（Power user）")
    ap.add_argument("--precheck-max-depth", type=int, default=None,
                    help="pre-check 搜索最大目录深度（未指定时用 [tool.mrs].precheck_max_depth，回退 15）")
    ap.add_argument("--dry-run", action="store_true", help="仅打印将执行的命令，不实际跑")
    ap.add_argument("--install-only", action="store_true", help="只安装 workflow 所需的 skill")
    ap.add_argument("--force-install", action="store_true", help="强制覆盖 ~/.claude/skills/ 下的旧版本")
    ap.add_argument("--yes", action="store_true", help="skill 安装遇到版本不一致时自动 yes")

    # TUI + 配置
    ap.add_argument("--ui", action="store_true", help="启动 TUI 配置界面（textual）")
    ap.add_argument("--no-config", action="store_true", help="不读取 [tool.mrs] 配置（仅用 CLI 参数）")
    return ap


def _ensure_tui_deps() -> None:
    """检查 TUI 依赖（仅 --ui 路径调用）。

    设计原则：TUI 只编辑配置，**不**自动 pip install —— 那会污染用户环境
    （PEP 668 系统需 --break-system-packages；venv 下可能错装到错误 site-packages）。
    缺包就 stderr 一行提示 + exit 2，让用户自己决定装法。
    """
    missing: list[str] = []
    try:
        import textual  # noqa: F401
    except ImportError:
        missing.append("textual")
    try:
        import tomlkit  # noqa: F401
    except ImportError:
        missing.append("tomlkit")
    if not missing:
        return
    print(
        f"[multi-review-scheduler] 缺 TUI 依赖: {', '.join(missing)}。"
        f"请手动执行：pip install multi-review-scheduler[tui]",
        file=sys.stderr,
    )
    sys.exit(2)


def _apply_config_defaults(args) -> None:
    """从 pyproject.toml [tool.mrs] 读配置，填充 args 中没显式指定的部分。

    优先级：CLI 显式值 > [tool.mrs] > argparse default（None 时走到 config 层）。
    argparse 把会被 config 覆盖的字段 default 设为 None，避免 magic-number 撞值。

    路径类字段（settings_* / project_root / log_path）从 config 写入 args 前
    先 ``expanduser()`` —— claude CLI 不展开 ``~``，否则 subprocess 会因
    "Settings file not found: ~/.claude/..." 失败。
    """
    try:
        from .config_io import find_config, load_config
    except ImportError:
        return
    cfg_path = find_config(Path.cwd())
    if not cfg_path:
        return
    cfg = load_config(cfg_path)

    def _set_if_none(attr: str, key: str) -> None:
        if getattr(args, attr, None) in (None, "", []):
            val = cfg.get(key)
            if val not in (None, ""):
                setattr(args, attr, val)

    _set_if_none("workflow", "default_workflow")
    _set_if_none("target", "default_target")
    _set_if_none("settings_b", "settings_b")
    _set_if_none("settings_a", "settings_a")
    _set_if_none("max_rounds", "max_rounds")  # argparse default=None；config 缺省 → runner fallback 3
    _set_if_none("b_extra", "b_extra")
    _set_if_none("a_extra", "a_extra")
    _set_if_none("project_root", "project_root")
    _set_if_none("timeout", "timeout_min")
    _set_if_none("log_path", "log_path")
    _set_if_none("precheck_max_depth", "precheck_max_depth")
    _set_if_none("heartbeat", "heartbeat_sec")
    _set_if_none("permission_mode", "permission_mode")
    # doc_class：config="auto" 是中性默认，不覆盖 CLI
    if not getattr(args, "doc_class", None):
        v = cfg.get("doc_class")
        if v and v != "auto":
            args.doc_class = v

    # 路径类字段：config 注入的字面 "~/" 必须展开（claude CLI 不认识 ~）
    for attr in ("settings_b", "settings_a", "settings", "project_root", "log_path"):
        v = getattr(args, attr, None)
        if v:
            setattr(args, attr, _expanduser_str(v))


def _expanduser_str(s: str | None) -> str | None:
    """对路径类参数做 ``~`` 展开。claude CLI 不展开 ``~``，会把带 ``~`` 的
    settings 路径当字面量报"file not found"——必须先展开。"""
    if not s:
        return s
    return str(Path(s).expanduser())


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # 路径参数统一 expanduser（claude CLI 不展开 ~）
    # log_path 故意不预填硬默认——保持 None 让 _apply_config_defaults 的
    # _set_if_none("log_path","log_path") 能接到 config 里的覆盖（F-3）
    args.settings_b = _expanduser_str(args.settings_b)
    args.settings_a = _expanduser_str(args.settings_a)
    args.settings   = _expanduser_str(args.settings)
    args.project_root = _expanduser_str(args.project_root)
    args.log_path   = _expanduser_str(args.log_path)

    if args.list_workflows:
        _print_workflows()
        return 0

    # ---- TUI 模式：启动配置界面 ----
    if args.ui:
        # 缺包 fail-fast；TUI 自身只编辑 pyproject.toml [tool.mrs]，不跑工作流
        _ensure_tui_deps()
        from .tui import run_tui
        run_tui()
        # TUI 已把配置写到 pyproject.toml；用户保存后自己跑
        # `multi-review-scheduler --target X` 即可，无需 --ui-run 标志
        return 0

    # F-6：删 TUI 路径的二次 expanduser 块（TUI L303 已 return 0 走不到，是死代码）
# 主流程的 expanduser 已在 L283-289 一次性做完；config 覆盖走 _apply_config_defaults

    # ---- 自动读 [tool.mrs] 配置 ----
    if not args.no_config:
        # --no-config 显式跳过；--ui 已 exit 不会走到这
        _apply_config_defaults(args)

    # ---- workflow 选择 ----
    driver = _resolve_workflow(args.workflow)

    # ---- install-only 早 return：不需要 target/exists 检查 ----
    if args.install_only:
        cfg = RunnerConfig(
            target=Path("."),
            driver=driver,
            workflow_config={},
            claude_cmd=args.claude_cmd,
            force_install=args.force_install,
            assume_yes=args.yes,
            install_only=True,
            log_path=Path(args.log_path or ".ab-review/run.log"),
        )
        return run(cfg)

    # ---- ab-review --reset 早 return：清 state.json 不需要 target ----
    if args.reset and args.workflow == "ab-review":
        cfg = RunnerConfig(
            target=Path("."),
            driver=driver,
            workflow_config={
                "reset": True,
                "resume": False,
                "max_rounds": args.max_rounds if args.max_rounds is not None else 3,
                "state_file": ".ab-review/state.json",
                "project_root": args.project_root,
            },
            claude_cmd=args.claude_cmd,
            log_path=Path(args.log_path or ".ab-review/run.log"),
            reset_only=True,
        )
        return run(cfg)

    if shutil.which(args.claude_cmd) is None:
        print(f"错误: 找不到 Claude Code CLI '{args.claude_cmd}'", file=sys.stderr)
        return 1
    if not args.target:
        print("错误: 必须指定 --target（或在 [tool.mrs] default_target 里写，或跑 `multi-review-scheduler --ui` 配置）",
              file=sys.stderr)
        return 1
    target = Path(args.target)
    if not target.exists():
        print(f"错误: 找不到目标 {target}", file=sys.stderr)
        return 1

    # ---- 准备 workflow_config（透传给 driver） ----
    workflow_config: dict = {}

    # 兜底：CLI 未传 + config 缺省 → 环境变量 / 硬默认
    max_rounds_eff = args.max_rounds if args.max_rounds is not None else 3
    timeout_eff = args.timeout if args.timeout is not None else DEFAULT_TIMEOUT
    log_path_eff = args.log_path or ".ab-review/run.log"
    precheck_max_depth_eff = args.precheck_max_depth if args.precheck_max_depth is not None else 15
    heartbeat_eff = args.heartbeat if args.heartbeat is not None else DEFAULT_HEARTBEAT
    permission_mode_eff = args.permission_mode if args.permission_mode is not None else DEFAULT_PERMISSION

    if args.workflow == "ab-review":
        model_b = _resolve_model("B", args.model_b, args.settings_b)
        model_a = _resolve_model("A", args.model_a, args.settings_a)
        workflow_config = {
            "target": str(target),
            "max_rounds": max_rounds_eff,
            "object_type": args.object_type,
            "range": args.range,
            "model_b": model_b,
            "model_a": model_a,
            "settings_b": args.settings_b,
            "settings_a": args.settings_a,
            "b_extra": args.b_extra,
            "a_extra": args.a_extra,
            "reset": args.reset,
            "resume": args.resume,
            "no_precheck_block": args.no_precheck_block,
            "precheck_max_depth": precheck_max_depth_eff,
            "state_file": ".ab-review/state.json",
            "project_root": args.project_root,
        }
    else:
        # single_skill 工作流
        model = _resolve_model("skill", args.model, args.settings)
        workflow_config = {
            "target": str(target),
            "model": model,
            "settings": args.settings,
            "project_root": args.project_root,
        }

    # ---- 跑 ----
    cfg = RunnerConfig(
        target=target,
        driver=driver,
        workflow_config=workflow_config,
        claude_cmd=args.claude_cmd,
        timeout_min=timeout_eff,
        heartbeat_sec=heartbeat_eff,
        permission_mode=permission_mode_eff,
        no_session_persistence=True,
        log_path=Path(log_path_eff),
        force_install=args.force_install,
        assume_yes=args.yes,
        dry_run=args.dry_run,
        install_only=False,
    )
    return run(cfg)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用户中断。state 保留，可重跑以继续。", file=sys.stderr)
        sys.exit(130)