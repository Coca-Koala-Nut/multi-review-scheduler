"""mrs-skill-rtl-analyze —— rtl-analyze skill 包。

作为独立 PyPI 包分发；通过 entry-point
``multi_review_scheduler.skills`` 注册 ``install`` 函数。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Literal

__version__ = "0.1.0"

_PKG_DIR = Path(__file__).resolve().parent

_RESOURCE_NAMES = (
    "SKILL.md",
    "README.md",
    "SUMMARY.md",
    "rtl_analyze_onepage.html",
)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _detect(target: Path) -> Literal["missing", "up_to_date", "differs", "error"]:
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
    """把 rtl-analyze skill 资源拷到 ``target``。"""
    target = Path(target)
    status = _detect(target)
    if status == "up_to_date":
        return "skipped"
    if status == "error":
        return "error"
    if status == "differs" and not force:
        return "differs"
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


def _selftest() -> None:
    print(f"mrs-skill-rtl-analyze {__version__}")
    print(f"package dir: {_PKG_DIR}")
    print(f"resources:   {[n for n in _RESOURCE_NAMES if (_PKG_DIR / n).exists()]}")


if __name__ == "__main__":
    _selftest()