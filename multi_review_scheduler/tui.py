"""TUI 配置界面（textual）。

启动：``multi-review-scheduler --ui`` 或 ``python3 -m multi_review_scheduler --ui``

行为：
- 启动时尝试从工程根 ``pyproject.toml`` 的 ``[tool.mrs]`` section 读配置
- 字段：target / workflow / settings_b / settings_a / max_rounds / b_extra / a_extra
        / project_root / doc_class / timeout_min / log_path
- 键盘：Q = Save & Quit  /  Esc = Quit (no save)  /  Tab 切换字段

依赖：``pip install multi-review-scheduler[tui]``（textual + tomlkit）
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from .config_io import FIELD_SPECS, load_config, save_config, find_config


HINT = "[Q] Save & Quit   [Esc] Quit (no save)   [Tab] 切字段"


def _build_app(init_cfg: dict[str, Any], cfg_file: Optional[Path]) -> Any:
    """构造 TUI App（延迟 import textual/tomlkit 依赖）。"""
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, VerticalScroll
        from textual.widgets import Input, Select, Static, Label
        from textual.binding import Binding
    except ImportError:
        print("[tui] 缺 textual/tomlkit，请 `pip install multi-review-scheduler[tui]`",
              file=sys.stderr)
        sys.exit(2)

    class MRSConfigApp(App):
        CSS = """
        Screen { layout: vertical; }
        #hint { dock: top; height: 1; background: $boost; color: $text; padding: 0 1; }
        #form { height: auto; padding: 1 2; }
        .row { height: 3; }
        .row Label { width: 22; padding: 1 1 0 0; }
        .row Input, .row Select { width: 1fr; }
        #footer { dock: bottom; height: 1; background: $boost; color: $text; padding: 0 1; }
        """

        BINDINGS = [
            Binding("q", "save_quit", "Save & Quit", priority=True),
            Binding("escape", "quit_nosave", "Quit (no save)", priority=True),
        ]

        def __init__(self, init_cfg: dict[str, Any], cfg_file: Optional[Path]) -> None:
            super().__init__()
            self._cfg = dict(init_cfg)
            self._cfg_file = cfg_file
            self._result: Optional[dict[str, Any]] = None

        def compose(self) -> "ComposeResult":
            yield Static(HINT, id="hint")
            with VerticalScroll(id="form"):
                for f in FIELD_SPECS:
                    with Horizontal(classes="row"):
                        yield Label(f.label + (" *" if f.key == "default_target" else ""))
                        if f.kind == "enum":
                            choices = [(str(c), c) for c in (f.choices or [])]
                            yield Select(choices, value=f.default, id=f"_w_{f.key}")
                        else:
                            ph = f.placeholder or f.help
                            yield Input(
                                value=str(self._cfg.get(f.key, f.default)),
                                placeholder=ph, id=f"_w_{f.key}",
                            )
            yield Static("", id="footer")

        def on_mount(self) -> None:
            self._refresh_footer(f"loaded: {self._cfg_file or '(new)'}")

        def _refresh_footer(self, msg: str) -> None:
            self.query_one("#footer", Static).update(msg)

        def _collect(self) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for f in FIELD_SPECS:
                w = self.query_one(f"#_w_{f.key}")
                if isinstance(w, Select):
                    val = w.value if w.value is not None else f.default
                else:
                    val = w.value
                if f.kind == "int":
                    try:
                        val = int(val) if val not in (None, "") else f.default
                    except (TypeError, ValueError):
                        val = f.default
                out[f.key] = val
            return out

        def _save(self) -> Optional[Path]:
            cfg = self._collect()
            # TUI 必填项：default_target 不空（不强制单字段，但 target 是工作流核心）
            if not (cfg.get("default_target") or "").strip():
                self._refresh_footer("⚠ default_target 不能为空；请填写目标文件路径")
                return None
            target = self._cfg_file or (Path.cwd() / "pyproject.toml")
            if not target.exists():
                target.write_text(
                    "[project]\nname = \"mrs-config\"\nversion = \"0.0.0\"\n",
                    encoding="utf-8",
                )
            save_config(target, cfg)
            return target

        def action_save_quit(self) -> None:
            p = self._save()
            if p is None:
                return
            self._result = self._collect()
            self._cfg_file = p
            self._refresh_footer(f"saved: {p}   → 退出")
            self.exit()

        def action_quit_nosave(self) -> None:
            self._result = None
            self.exit()

    return MRSConfigApp(init_cfg, cfg_file)  # type: ignore[call-arg]


def run_tui() -> dict[str, Any]:
    """启动 TUI，返回用户最终确认的 config dict。"""
    cfg_path = find_config(Path.cwd())
    initial = load_config(cfg_path) if cfg_path else {
        f.key: f.default for f in FIELD_SPECS
    }
    app = _build_app(initial, cfg_path)
    app.run()
    return app._result or initial


# 顶层别名，便于 Pilot 模式 / 单元测试 import
def get_app_class():
    """返回 MRSConfigApp 类（不实例化；用于测试）。"""
    cfg_path = find_config(Path.cwd())
    initial = load_config(cfg_path) if cfg_path else {
        f.key: f.default for f in FIELD_SPECS
    }
    # 内部用 _build_app 但只取 class
    try:
        from textual.app import App
    except ImportError:
        return None
    return _build_app(initial, cfg_path).__class__


__all__ = ["run_tui", "get_app_class", "HINT"]