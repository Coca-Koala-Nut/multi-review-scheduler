"""TOML 配置读写（pyproject.toml [tool.mrs] section）。

用 tomlkit 保证读和写都保留 pyproject.toml 的注释、格式、其他 section；
读失败（tomlkit 兼容性 / 文件不存在 / 无 [tool.mrs]）一律降级返回空 config。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


SECTION = "tool.mrs"

# ---- 字段定义（顺序即 TUI 显示顺序） ----
@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str          # "str" | "int" | "path" | "enum" | "bool"
    default: Any
    choices: Optional[list[Any]] = None
    placeholder: str = ""
    help: str = ""


FIELD_SPECS: list[FieldSpec] = [
    FieldSpec("default_target", "目标文件", "path", "",
              placeholder="必填，如 CordicVect_analysis.md",
              help="TUI 必填：工作流的目标文件路径；留空 TUI 会拒绝保存。运行时可用 --target 覆盖。"),
    FieldSpec("default_workflow", "默认 workflow", "enum", "ab-review",
              choices=["ab-review", "rtl-analyze"],
              help="TUI 启动时预选；也可用 --workflow 覆盖"),
    FieldSpec("settings_b", "B 角色 settings.json", "path", "",
              placeholder="如 ~/.claude/settings-db-kimi.json",
              help="ab-review 用；推断 B 模型。留空：靠 _read_model_from_settings 返回 None → _resolve_model 提示。"),
    FieldSpec("settings_a", "A 角色 settings.json", "path", "",
              placeholder="如 ~/.claude/settings-ds.json",
              help="ab-review 用；推断 A 模型。留空：同上。"),
    FieldSpec("max_rounds", "最大轮次", "int", 3,
              help="ab-review 用；范围 1-10"),
    FieldSpec("b_extra", "B 角色额外提示", "str", "",
              placeholder="如 '重点看时序'"),
    FieldSpec("a_extra", "A 角色额外提示", "str", ""),
    FieldSpec("project_root", "项目根（搜索范围）", "path", "",
              placeholder="留空=自动",
              help="留空时自动用 git 仓库根 / CLAUDE.md 所在目录；指定路径会覆盖自动检测。"),
    FieldSpec("doc_class", "文档分类", "enum", "auto",
              choices=["auto", "with-code", "standalone"],
              help="auto = 按文件名自动；其它 = 强制"),
    FieldSpec("timeout_min", "单步超时（分）", "int", 30),
    FieldSpec("log_path", "日志路径", "path", ".ab-review/run.log"),
    FieldSpec("precheck_max_depth", "pre-check 搜索深度", "int", 15,
              help="doc-with-code 找配套 RTL 源的最大目录层数。SoC IP 经常深达 9-12 层，默认 15 够用。"),
    FieldSpec("heartbeat_sec", "心跳间隔（秒）", "int", 30,
              help="runner 进程心跳打印间隔；环境变量 MRS_HEARTBEAT_SEC 兜底。"),
    FieldSpec("permission_mode", "claude --permission-mode", "str", "auto",
              placeholder="auto / accept-edits / plan / …",
              help="传给 claude --permission-mode；环境变量 MRS_PERMISSION_MODE 兜底。"),
]


def _default_config() -> dict[str, Any]:
    return {f.key: f.default for f in FIELD_SPECS}


def _import_tomlkit():
    try:
        import tomlkit
        return tomlkit
    except ImportError:
        print("[config_io] 缺 tomlkit，请 `pip install multi-review-scheduler[tui]`",
              file=sys.stderr)
        sys.exit(2)


def load_config(path: Path) -> dict[str, Any]:
    """从 ``path``（一般是 pyproject.toml）读 [tool.mrs] section；不存在返回默认。"""
    cfg = _default_config()
    if not path.exists():
        return cfg
    tomlkit = _import_tomlkit()
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[config_io] 解析 {path} 失败：{e}；使用默认", file=sys.stderr)
        return cfg
    # tomlkit 的访问：[tool][mrs] 嵌套
    sec = doc.get("tool", {}).get("mrs") if isinstance(doc, dict) else None
    if not isinstance(sec, dict):
        return cfg
    for f in FIELD_SPECS:
        if f.key in sec:
            cfg[f.key] = sec[f.key]
    return cfg


def save_config(path: Path, cfg: dict[str, Any]) -> None:
    """把 cfg 写回 [tool.mrs]；保留 pyproject 其他 section 与注释。"""
    tomlkit = _import_tomlkit()
    if path.exists():
        try:
            doc = tomlkit.parse(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[config_io] 解析 {path} 失败，将新建：{e}", file=sys.stderr)
            doc = tomlkit.document()
    else:
        doc = tomlkit.document()
    # 确保 [tool] 和 [tool.mrs] 存在
    if "tool" not in doc or not isinstance(doc.get("tool"), dict):
        doc["tool"] = tomlkit.table()
    if "mrs" not in doc["tool"] or not isinstance(doc["tool"].get("mrs"), dict):
        doc["tool"]["mrs"] = tomlkit.table()
    sec = doc["tool"]["mrs"]
    for f in FIELD_SPECS:
        val = cfg.get(f.key, f.default)
        if val == "" or val is None:
            continue  # 留空不写
        sec[f.key] = val
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def find_config(start: Path) -> Optional[Path]:
    """向上找 ``pyproject.toml``（含 [tool.mrs] section 才返回）。

    用 tomlkit 解析后 ``doc.get("tool", {}).get("mrs") is not None`` 判断；
    不再用 FIELD_SPECS 默认值启发（脆弱：用户改 default 值就漏判）。
    """
    cur = start.resolve() if start.is_file() else start.resolve()
    if cur.is_file():
        cur = cur.parent
    for ancestor in [cur, *cur.parents]:
        p = ancestor / "pyproject.toml"
        if not p.exists():
            continue
        try:
            tomlkit = _import_tomlkit()
            doc = tomlkit.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # tomlkit 访问：doc["tool"]["mrs"] 嵌套（container 类型为 tomlkit.items.Table）
        tool = doc.get("tool") if isinstance(doc, dict) else None
        if isinstance(tool, dict) and isinstance(tool.get("mrs"), dict):
            return p
    return None


__all__ = ["FIELD_SPECS", "FieldSpec", "load_config", "save_config", "find_config", "SECTION"]