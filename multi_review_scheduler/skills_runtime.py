"""Skill 发现与安装运行时。

通过 ``importlib.metadata.entry_points`` 找
``multi_review_scheduler.skills`` 组下的所有 skill 包，调它们各自的
``install(target)`` 函数。

设计要点：
- 不再内嵌 skill；skill 是独立 PyPI 包。
- 找不到 entry_point（用户没装对应 skill 包）时，fallback 检查
  ``~/.claude/skills/<name>/`` 是否已有；都没有才报 error，并提示
  ``pip install multi-review-scheduler[<extras>]``。
- 完全静态；不修改 sys.path、不依赖文件存在性。
"""

from __future__ import annotations

import importlib.metadata as md
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

__all__ = [
    "SKILL_TARGET",
    "SKILL_ENTRY_POINT_GROUP",
    "EXTRAS_BY_SKILL",
    "discover",
    "list_packaged_skills",
    "is_installed",
    "install",
    "install_skills",
]


SKILL_TARGET = Path.home() / ".claude" / "skills"
SKILL_ENTRY_POINT_GROUP = "multi_review_scheduler.skills"

# skill 名 → 主包 extra 的映射；用于友好提示用户装哪个 extra。
EXTRAS_BY_SKILL: dict[str, str] = {
    "ab-review": "ab-review",
    "rtl-analyze": "rtl",
}


def _has_skill_md(skill_dir: Path) -> bool:
    return (skill_dir / "SKILL.md").is_file()


# ---- 发现 ----
def discover() -> dict[str, md.EntryPoint]:
    """返回 ``{skill_name: entry_point}`` 映射，仅含当前进程可见的。"""
    try:
        eps = md.entry_points(group=SKILL_ENTRY_POINT_GROUP)
    except Exception as e:
        print(f"[skills_runtime] entry_points 加载失败: {e}", file=sys.stderr)
        return {}
    return {ep.name: ep for ep in eps}


def list_packaged_skills() -> list[str]:
    """所有已被 pip 装到当前环境的 skill 名（按字母序）。"""
    return sorted(discover().keys())


# ---- 状态检测 ----
def is_installed(name: str) -> bool:
    """快速检查 ``~/.claude/skills/<name>/`` 是否有 SKILL.md。"""
    return _has_skill_md(SKILL_TARGET / name)


# ---- 安装 ----
def install(
    name: str,
    *,
    force: bool = False,
    assume_yes: bool = False,
    out=sys.stderr,
) -> str:
    """安装单个 skill 到 ``~/.claude/skills/<name>/``。

    返回状态（与 ``engine.installer`` 对齐）：
    - ``installed``  全新安装
    - ``skipped``    已存在且内容一致
    - ``updated``    已覆盖
    - ``differs``    已存在但内容不同，未覆盖（提示用户）
    - ``error``      没 entry_point、没本地资源、目标不可写
    """
    target = SKILL_TARGET / name
    eps = discover()

    if name in eps:
        install_fn: Callable = eps[name].load()
        try:
            status = install_fn(target, force=force)
        except Exception as e:
            print(f"[skills_runtime] {name}.install() 抛错: {e}", file=out)
            return "error"
        # "differs" → 询问用户（除非 assume_yes/force）
        if status == "differs":
            if force or assume_yes:
                return install_fn(target, force=True)
            try:
                ans = input(f"[skills_runtime] {name} 已存在且内容不同，是否覆盖？[y/N] ").strip().lower()
            except EOFError:
                ans = "n"
            if ans == "y":
                return install_fn(target, force=True)
            print(f"[skills_runtime] 跳过 {name}", file=out)
            return "skipped"
        if status == "error":
            print(f"[skills_runtime] {name} install() 报 error", file=out)
        return status

    # 没找到 entry_point：fallback 到本地 ~/.claude/skills/ 已有
    if _has_skill_md(target):
        print(f"[skills_runtime] {name} 未注册 entry_point 但本地已存在，沿用 {target}", file=out)
        return "skipped"

    # 真没
    extra = EXTRAS_BY_SKILL.get(name)
    hint = (
        f"提示: pip install multi-review-scheduler[{extra}]"
        if extra
        else f"提示: pip install mrs-skill-{name}"
    )
    print(
        f"[skills_runtime] {name} 未注册 entry_point 且本地未装。{hint}",
        file=out,
    )
    return "error"


def install_skills(
    names: Iterable[str],
    *,
    force: bool = False,
    assume_yes: bool = False,
) -> dict[str, str]:
    return {n: install(n, force=force, assume_yes=assume_yes) for n in names}