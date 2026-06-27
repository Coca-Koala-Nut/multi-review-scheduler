#!/usr/bin/env python3
"""mrs-bootstrap —— 一行启动 multi-review-scheduler TUI。

新用户在新电脑上：

    # 通过网络（发布到 GitHub raw / 内网 HTTP 后替换 URL）
    curl -sSL https://raw.githubusercontent.com/Coca-Koala-Nut/multi-review-scheduler/main/mrs-bootstrap.py | python3 -

    # 本地 / 离线
    python3 mrs-bootstrap.py

    # 或已下到本地
    ./mrs-bootstrap.py

行为：
1. 检测 Python ≥ 3.9
2. 检测 pip 可用（含 PEP 668 / venv 适配）
3. 检测当前是否已装 multi-review-scheduler；未装则
   ``pip install --user multi-review-scheduler[full]``
4. 调 ``multi-review-scheduler --ui``（在它自己的上下文里）

设计原则：std lib only，零依赖；不会因为缺东西崩溃。

注意：F-3 之后 ``--ui`` 自身**不**自动 pip install（避免污染用户环境）。
所以这个 bootstrap 是**唯一**仍然自动 pip 的入口；老用户直接用 ``--ui`` 即可。
``[full]`` 包含主包 + ab-review + rtl-analyze + textual + tomlkit，一次装齐。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PY = (3, 9)
PKG = "multi-review-scheduler"
EXTRAS = "[full]"  # 包含主包 + 2 skill + textual + tomlkit


def _info(msg: str) -> None:
    print(f"[mrs-bootstrap] {msg}", flush=True)


def _err(msg: str) -> None:
    print(f"[mrs-bootstrap] {msg}", file=sys.stderr, flush=True)


def check_python() -> None:
    if sys.version_info < MIN_PY:
        _err(f"需要 Python {MIN_PY[0]}.{MIN_PY[1]}+ ，当前 {sys.version_info[0]}.{sys.version_info[1]}")
        sys.exit(1)
    _info(f"Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} OK")


def check_pip() -> str:
    """返回可用的 pip 命令（含 --user / --break-system-packages 选项）。"""
    # 1) python -m pip
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if r.returncode == 0:
            pip_cmd = [sys.executable, "-m", "pip"]
        else:
            raise RuntimeError
    except Exception:
        # 2) 找 PATH 里的 pip
        which = shutil.which("pip") or shutil.which("pip3")
        if not which:
            _err("找不到 pip。请先 `python3 -m ensurepip` 或装 python3-pip。")
            sys.exit(2)
        pip_cmd = [which]

    # 检测是否需要 --break-system-packages（Debian PEP 668）
    is_debian_pep668 = False
    try:
        import sysconfig
        # 简单判断：Debian/Ubuntu 系统 Python 路径常以 /usr/lib/python3.* 开头
        if sys.prefix.startswith("/usr") and Path("/etc/debian_version").exists():
            is_debian_pep668 = True
    except Exception:
        pass

    if is_debian_pep668:
        pip_cmd += ["--break-system-packages"]

    # 检测 venv：venv 装时不需要 --user
    is_venv = (sys.prefix != sys.base_prefix) or hasattr(sys, "real_prefix")
    if not is_venv and not is_debian_pep668:
        pip_cmd += ["--user"]

    return pip_cmd


def is_installed() -> bool:
    try:
        __import__("multi_review_scheduler")
        return True
    except ImportError:
        return False


def _find_local_project() -> Path | None:
    """检测当前是否在 multi-review-scheduler 工程内（含 pyproject.toml + 名字匹配）。

    用于无 PyPI 时的本地 ``pip install -e .[full]`` 模式。
    """
    cur = Path.cwd().resolve()
    for ancestor in [cur, *cur.parents]:
        pp = ancestor / "pyproject.toml"
        if not pp.exists():
            continue
        try:
            text = pp.read_text(encoding="utf-8", errors="ignore")
            if 'name = "multi-review-scheduler"' in text or "name = 'multi-review-scheduler'" in text:
                return ancestor
        except OSError:
            continue
    return None


def install(pip_cmd: list[str]) -> None:
    local = _find_local_project()
    if local:
        _info(f"检测到本地工程 {local}，用 editable 模式装…")
        cmd = pip_cmd + ["install", "-e", f"{local}{EXTRAS}"]
    else:
        _info(f"正在 pip install {PKG}{EXTRAS} …")
        cmd = pip_cmd + ["install", "--upgrade", f"{PKG}{EXTRAS}"]
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        _err("pip install 失败。常见原因：")
        _err("  - 网络问题 → 配 pip 源 / proxy")
        _err("  - 权限问题 → 用 venv 或 sudo")
        _err(f"  - 手动试：{' '.join(cmd)}")
        sys.exit(3)


def launch_ui() -> int:
    """装好后调 ``multi-review-scheduler --ui``。"""
    from multi_review_scheduler import main
    return main(["--ui"])


def main() -> int:
    check_python()
    pip_cmd = check_pip()
    if not is_installed():
        _info(f"未检测到 {PKG}，开始安装…")
        install(pip_cmd)
        # 重新 import
        for mod in list(sys.modules):
            if mod.startswith("multi_review_scheduler"):
                del sys.modules[mod]
    else:
        _info(f"{PKG} 已装，启 TUI…")
    return launch_ui()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _err("\n用户中断")
        sys.exit(130)