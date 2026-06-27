"""工程根识别 + 受控搜索。

供 ABReviewDriver / SingleSkillDriver 在 pre-check 阶段使用：
- ``find_project_root()``：按优先级链识别工程根
- ``search_project()``：在工程根下 Glob / Grep，自动排除噪音目录
- ``extract_stems()``：从 target 文件名抽候选关键词

设计原则：
- 纯标准库 + 已有依赖；不引第三方。
- 失败一律降级到 cwd，不抛异常（pre-check 失败不该阻塞 init）。
- 噪音目录用 fnmatch 模式匹配，覆盖 ``.git``/``__pycache__``/``node_modules``
  /``.ab-review``/``.workflow``/``.venv``/``*.egg-info``/``dist``/``build``。
"""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

# ---------- 噪音目录匹配 ----------
# 目录名（完整匹配）或 fnmatch 模式（带通配符）。
DEFAULT_IGNORES: tuple[str, ...] = (
    ".git",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".ab-review",
    ".workflow",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "*.egg-info",
    "*.pyc",
    "*.o",
)


def _is_ignored(part: str) -> bool:
    for pat in DEFAULT_IGNORES:
        if fnmatch.fnmatch(part, pat):
            return True
    return False


# ---------- 工程根识别 ----------
def find_project_root(start: Path | None = None) -> Path:
    """按 cwd 优先 + fallback 上溯识别工程根（Path）：

    1. ``start`` / cwd 起步：cwd 下有 ``pyproject.toml`` → 直接锁定
    2. cwd 没 pyproject → 沿父目录上溯，按 git 根 → CLAUDE.md 父 → .ab-review
       父 → .git 父 顺序找，命中即停
    3. fallback：返回 cwd（永不抛异常）

    行为符合用户直觉："我在哪敲命令，工程根就是哪；找不到再上溯"。
    ``--project-root`` 显式覆盖（最高优先级，driver 层处理）。
    """
    if start is None:
        start = Path.cwd()
    start = Path(start).resolve()
    cur = start if start.is_dir() else start.parent

    # 1) cwd 优先：有 pyproject 就锁定（不打扰用户的工程结构判断）
    if (cur / "pyproject.toml").is_file():
        return cur

    # 2) cwd 没 pyproject → fallback 上溯
    # 2a) git 根（最近的祖先）
    if shutil.which("git"):
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=cur, capture_output=True, text=True, check=False, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                p = Path(r.stdout.strip())
                if p.is_dir():
                    return p
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 2b) 向上 find CLAUDE.md / .ab-review / .git 父目录（按祖先顺序，命中最近）
    for ancestor in [cur, *cur.parents]:
        if (ancestor / "CLAUDE.md").is_file():
            return ancestor
        if (ancestor / ".ab-review").is_dir():
            return ancestor
        if (ancestor / ".git").exists():
            return ancestor

    # 3) fallback：cwd
    return cur


# ---------- 受控搜索 ----------
def search_project(
    root: Path,
    patterns: Iterable[str],
    *,
    extra_ignores: Iterable[str] = (),
    max_depth: int = 15,
    follow_symlinks: bool = False,
) -> list[Path]:
    """在 ``root`` 下 Glob 多个模式，自动跳过噪音目录和超深路径。

    ``max_depth`` 默认 15 —— SoC IP 目录经常深达 9-12 层
    （IPs/HW/<proj>/<block>/<sub>/<subsub>/verilog/rtl/），
    原 8 太浅导致漏搜。返回绝对路径列表（按字母序）。
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return []
    ignores = tuple(extra_ignores)
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        for path in root.glob(pat):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue  # 在 root 外
            if len(rel.parts) > max_depth:
                continue
            if any(_is_ignored(p) for p in rel.parts):
                continue
            if not follow_symlinks and path.is_symlink():
                continue
            ap = path.resolve()
            if ap in seen:
                continue
            seen.add(ap)
            out.append(ap)
    out.sort()
    return out


def grep_project(
    root: Path,
    pattern: str,
    *,
    includes: Iterable[str] = ("*.v", "*.sv", "*.vhd", "*.vhdl"),
    extra_ignores: Iterable[str] = (),
    max_depth: int = 15,
) -> list[Path]:
    """Grep ``pattern`` 在 ``root`` 下匹配的文件列表。

    F-9: 保留此函数（pre-check 当前用 search_project + 文件名匹配，不需要 grep 内容；
    但未来可能用于"搜 body 里写了某 module 名但文件名不对"场景，所以保留 std-lib 实现）。
    不用 ripgrep；用纯 Python 简单实现（性能可接受，因为是 pre-check）。
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return []
    out: list[Path] = []
    seen: set[Path] = set()
    for inc in includes:
        for path in search_project(root, [f"**/{inc}"], extra_ignores=extra_ignores, max_depth=max_depth):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pattern in text and path not in seen:
                seen.add(path)
                out.append(path)
    return out


# ---------- 关键词抽取 ----------
_DOC_SUFFIXES = (
    "_analysis", "_analysis_doc", "_note", "_notes",
    "_spec", "_doc", "_review", "_readme",
)


# ---------- 目标分类 ----------
# 三类 + 一个 fallback：
# - "rtl"            : 代码自身 → 走 rtl-analyze 建议+提醒协议
# - "doc-with-code"  : 配套有代码的说明/分析文档（_analysis / _design / _spec ...）→ 强制阻塞
# - "standalone-doc" : 自包含文档（学习手册 / 教程 / 概览 / 笔记 ...）→ 完全跳过配对
# - "unknown-doc"    : 文档但无法判定归属 → 保守走 doc-with-code 协议（强制阻塞）
# F-10: .bak 太通用（任何编辑器都可能生成 foo.v.bak），不当 RTL 处理。
# 如有备份需求，命名为 foo.bak.v 或 foo.v.bak 仍能被 .v 后缀命中。
_RTL_EXTS = {".v", ".sv", ".vhd", ".vhdl", ".svh", ".inc"}

# standalone-doc 关键词（lowercase 子串匹配；中文不分大小写）
_STANDALONE_DOC_KEYWORDS = (
    # 中文
    "学习手册", "教程", "概览", "笔记", "速查", "手册",
    "入门", "总结", "摘要", "总览", "指南", "实践", "经验",
    "知识", "学习笔记", "学习指南", "最佳实践",
    # English
    "tutorial", "handbook", "guide", "manual", "notes",
    "readme", "overview", "intro", "introduction",
    "summary", "cheatsheet", "cheat-sheet", "glossary",
    "faq", "best_practices", "best-practices",
    "primer", "fundamentals", "basics",
)

# doc-with-code 关键词（lowercase 子串/后缀匹配）
_DOC_WITH_CODE_KEYWORDS = (
    # English suffix
    "_analysis", "_design", "_spec", "_review", "_doc",
    "_interface", "_arch", "_architecture",
    "_impl", "_implementation", "_module",
    "_rtl", "_coding",
    # English prefix
    "design_", "analysis_", "spec_",
    "module_", "rtl_",
    # 中文（子串匹配；典型文档标题）
    "设计文档", "设计说明", "分析报告", "实现文档",
    "接口说明", "架构文档", "评审报告", "模块说明",
)


def classify_target(target: Path) -> str:
    """把 target 分成 ``rtl`` / ``doc-with-code`` / ``standalone-doc`` / ``unknown-doc``。

    规则：
    1. 扩展名命中 ``_RTL_EXTS`` → ``rtl``
    2. 否则按文件名 stem 关键词匹配
       - 含 ``_STANDALONE_DOC_KEYWORDS`` 中任一 → ``standalone-doc``
       - 含 ``_DOC_WITH_CODE_KEYWORDS`` 中任一 → ``doc-with-code``
    3. 都不是 → ``unknown-doc``（保守走 doc-with-code 协议）
    """
    ext = target.suffix.lower()
    if ext in _RTL_EXTS:
        return "rtl"
    stem = target.stem
    lower = stem.lower()
    for kw in _STANDALONE_DOC_KEYWORDS:
        if kw.lower() in lower:
            return "standalone-doc"
    for kw in _DOC_WITH_CODE_KEYWORDS:
        if kw.lower() in lower:
            return "doc-with-code"
    return "unknown-doc"


def extract_stems(target: Path) -> list[str]:
    """从 ``target`` 抽候选关键词（保序去重）。

    策略：
    1. 文件名 stem 优先（保底一定有内容）
    2. 读文档 body 抽模块名：
       - Markdown 标题 ``## Module FooBar`` / ``### FooBar``
       - 代码块语言标签 `` ```sv`` / `` ```systemverilog``
       - 反引号 `` `FooBar` `` （短词、含大写）
       - 显式声明 ``module: FooBar`` / ``module FooBar``
    3. 后缀剥离（_analysis / _spec / ...）

    例：
    - ``CordicVect_analysis.md``（body 提"模块 CordicVect_top"）
      → ``["CordicVect_analysis", "CordicVect", "CordicVect_top"]``
    - ``top.sv`` → ``["top"]``
    """
    stem = target.stem
    out: list[str] = [stem]
    lower = stem.lower()
    for suf in _DOC_SUFFIXES:
        if lower.endswith(suf) and len(stem) > len(suf):
            out.append(stem[: -len(suf)])
            break

    # 读 body 抽模块名（仅文档类目标；RTL 文件不需要 —— 自己就是模块）
    if target.suffix.lower() in _RTL_EXTS:
        seen: set[str] = set()
        return [s for s in out if not (s in seen or seen.add(s))]

    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        seen = set()
        return [s for s in out if not (s in seen or seen.add(s))]

    # 只看前 200 行（pre-check 不能太贵；模块名一般在前几节）
    head = "\n".join(text.splitlines()[:200])

    import re
    # 1) Markdown 标题里的 PascalCase / snake_case 词
    for m in re.finditer(r"^#{1,6}\s+([A-Za-z_][A-Za-z0-9_]+)", head, re.MULTILINE):
        tok = m.group(1)
        if _looks_like_module(tok):
            out.append(tok)
    # 2) 反引号包裹的标识符 —— 只收看起来像模块的（PascalCase ≥2 大写 / snake_case ≥2 下划线）
    for m in re.finditer(r"`([A-Za-z_][A-Za-z0-9_]{2,40})`", head):
        tok = m.group(1)
        if _looks_like_module(tok):
            out.append(tok)
    # 3) 显式声明 module: Foo / module Foo
    for m in re.finditer(r"\bmodule[:\s]+([A-Za-z_][A-Za-z0-9_]+)", head):
        tok = m.group(1)
        if _looks_like_module(tok):
            out.append(m.group(1))
    # 4) 代码块语言标签（sv / systemverilog / vhdl）→ 不直接当模块，但标记文档是 RTL 相关
    for m in re.finditer(r"^```(sv|systemverilog|v|vhdl|verilog)\b", head, re.MULTILINE):
        # 不加 token；只是信号 —— 由 caller 决定要不要进一步搜
        pass

    seen = set()
    return [s for s in out if not (s in seen or seen.add(s))]


def _looks_like_module(tok: str) -> bool:
    """启发式：像模块名的 token 才保留。

    模块名典型形态：
    - PascalCase 且 ≥2 个大写字母（FooBar / CordicVectTop）
    - snake_case 且 ≥2 个下划线（cordic_vect_top / foo_bar_baz）
    - 全大写且 ≥2 字符（CORDIC / FIFO）

    排除：
    - 单大写+小写单词（Load / Flag / DataIn → 通常是 signal 名）
    - 全小写单词（int / type → 通常是关键字）
    """
    if len(tok) < 3:
        return False
    upper = sum(1 for c in tok if c.isupper())
    if upper >= 2:
        return True
    if tok.isupper():
        return True
    if tok.count("_") >= 2:
        return True
    return False


__all__ = [
    "DEFAULT_IGNORES",
    "find_project_root",
    "search_project",
    "grep_project",
    "extract_stems",
]