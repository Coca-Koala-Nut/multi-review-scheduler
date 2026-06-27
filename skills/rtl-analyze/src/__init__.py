"""mrs-skill-rtl-analyze —— rtl-analyze skill 包（占位骨架）。

作为独立 PyPI 包分发；通过 entry-point
``multi_review_scheduler.skills`` 注册 ``install`` 函数，
由 ``multi-review-scheduler`` 的 ``skills_runtime`` 调用，把本包内
嵌的资源（SKILL.md）拷到 ``~/.claude/skills/rtl-analyze/``。

当前为占位版本；SKILL.md 仅含最小定义，Claude 加载后会提示能力未就绪。
补充真实 skill 时直接替换 SKILL.md 即可。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

__version__ = "0.1.0"

_PKG_DIR = Path(__file__).resolve().parent

_RESOURCE_NAMES = (
    "SKILL.md",
    "README.md",
)


def install(
    target: Path,
    *,
    force: bool = False,
) -> Literal["installed", "skipped", "updated", "error"]:
    """把 rtl-analyze skill 资源拷到 ``target``。

    ``target`` 通常是 ``~/.claude/skills/rtl-analyze/``。
    """
    target = Path(target)
    src_skill_md = _PKG_DIR / "SKILL.md"
    if not src_skill_md.exists():
        return "error"

    target_skill_md = target / "SKILL.md"
    if target_skill_md.exists() and not force:
        return "skipped"

    if target.exists() and force:
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in _RESOURCE_NAMES:
        src = _PKG_DIR / name
        if not src.exists():
            continue
        dst = target / name
        if src.is_dir():
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        else:
            shutil.copy2(src, dst)
    return "installed" if not target_skill_md.exists() or force else "updated"
