"""mrs-skill-ab-review —— ab-review skill 包。

作为独立 PyPI 包分发；通过 entry-point
``multi_review_scheduler.skills`` 注册 ``install`` 函数，
由 ``multi-review-scheduler`` 的 ``skills_runtime`` 调用，把本包内
嵌的资源（SKILL.md / scripts/...）拷到 ``~/.claude/skills/ab-review/``。

设计要点：
- ``install`` 函数幂等；用 SKILL.md sha256 比对判定版本是否一致。
- 不写日志、不交互询问；上层（runtime）根据返回值决定是否提示用户。
- 返回值在 ``{"installed", "skipped", "updated", "differs", "error"}`` 中。
- 包本身可独立 ``pip install``，亦可 ``pip install multi-review-scheduler[ab-review]`` 一起装。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Literal

__version__ = "0.1.0"

_PKG_DIR = Path(__file__).resolve().parent

# 包内实际会拷给 skill 运行时使用的资源子集（自动跳过不存在的）。
_RESOURCE_NAMES = (
    "SKILL.md",
    "README.md",
    "REFERENCE.md",
    "SUMMARY.md",
    "ab_review_onepage.html",
    "scripts",
)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _detect(target: Path) -> Literal["missing", "up_to_date", "differs", "error"]:
    """检查目标 skill 目录状态。"""
    target_skill_md = target / "SKILL.md"
    src_skill_md = _PKG_DIR / "SKILL.md"
    if not src_skill_md.exists():
        return "error"
    if not target_skill_md.exists():
        return "missing"
    if _sha256(src_skill_md) == _sha256(target_skill_md):
        return "up_to_date"
    return "differs"


def install(
    target: Path,
    *,
    force: bool = False,
) -> Literal["installed", "skipped", "updated", "differs", "error"]:
    """把 ab-review skill 资源拷到 ``target``。

    ``target`` 通常是 ``~/.claude/skills/ab-review/``。

    返回值：
    - ``installed`` 全新安装
    - ``skipped``   已存在且内容一致
    - ``updated``   已存在且已覆盖（仅在 ``force=True`` 或初次之外重装时）
    - ``differs``   已存在但内容不同，**未覆盖**（runtime 应询问用户）
    - ``error``     资源缺失或目标不可写
    """
    target = Path(target)
    status = _detect(target)
    if status == "up_to_date":
        return "skipped"
    if status == "error":
        return "error"
    if status == "differs" and not force:
        return "differs"

    # missing 或 force=True 或 differs+force：执行安装/覆盖
    if target.exists():
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
    return "installed" if status == "missing" else "updated"


# 让 ``python3 -m mrs_skill_ab_review`` 也能打印一些自检信息
def _selftest() -> None:
    print(f"mrs-skill-ab-review {__version__}")
    print(f"package dir: {_PKG_DIR}")
    print(f"resources:   {[n for n in _RESOURCE_NAMES if (_PKG_DIR / n).exists()]}")


if __name__ == "__main__":
    _selftest()