"""通用工作流主循环。

负责：skill 安装、日志（stdout + ``.ab-review/run.log``）、驱动初始化、
循环 ``driver.next_step`` → ``claude -p`` 调度、心跳、超时、Ctrl+C
安全终止。

driver 只关心 state 推进与 prompt 生成；runner 负责真实地起 claude 子进程。
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from drivers.base import Step, WorkflowDriver
from multi_review_scheduler import skills_runtime as _skills_runtime

CLAUDE_CMD = os.environ.get("CLAUDE_CMD", "claude")
DEFAULT_TIMEOUT_MIN = int(os.environ.get("MRS_TIMEOUT_MIN", "30"))
DEFAULT_PERMISSION = os.environ.get("MRS_PERMISSION_MODE", "auto")
DEFAULT_HEARTBEAT_SEC = int(os.environ.get("MRS_HEARTBEAT_SEC", "30"))


# ---------------------- 日志 Tee ----------------------
class _Tee:
    def __init__(self, stream, path: Path):
        self.stream = stream
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, "a", encoding="utf-8")

    def write(self, data):
        self.stream.write(data)
        self.file.write(data)
        self.file.flush()

    def flush(self):
        self.stream.flush()
        self.file.flush()

    def isatty(self):
        return getattr(self.stream, "isatty", lambda: False)()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()


def _setup_logging(log_path: Path) -> None:
    sys.stdout = _Tee(sys.stdout, log_path)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] runner 启动，PID {os.getpid()}")
    sys.stdout.flush()


# ---------------------- 子进程调度 ----------------------
_active_proc: subprocess.Popen | None = None


def _kill_active():
    global _active_proc
    if _active_proc is not None and _active_proc.poll() is None:
        _active_proc.terminate()
        try:
            _active_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _active_proc.kill()
            _active_proc.wait()
    _active_proc = None


def _sigint_handler(signum, frame):
    print("\n\n收到中断信号，正在终止当前 Claude 进程…", file=sys.stderr)
    _kill_active()
    sys.exit(130)


def _build_cmd(step: Step, claude_cmd: str, permission_mode: str | None, no_session: bool) -> list[str]:
    cmd: list[str] = [claude_cmd]
    if step.settings:
        cmd += ["--settings", str(step.settings)]
    if step.model:
        cmd += ["--model", step.model]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    if no_session:
        cmd += ["--no-session-persistence"]
    cmd += ["-p", step.prompt]
    return cmd


def _stream_claude(
    cmd: list[str],
    label: str,
    timeout_sec: int,
    heartbeat_sec: int,
    cwd: Path | None,
    extra_env: dict[str, str],
) -> int:
    """流式执行 claude -p，带超时 + 心跳。返回退出码（-1 表示超时）。"""
    global _active_proc
    start = time.monotonic()
    ts = time.strftime("%H:%M:%S")
    print(f"\n[{label}][{ts}] 启动: {' '.join(shlex.quote(c) for c in cmd)}")
    sys.stdout.flush()

    env = os.environ.copy()
    env.update(extra_env)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    _active_proc = proc
    print(f"[{label}] 子进程 PID: {proc.pid}", flush=True)
    timed_out = threading.Event()
    stop_hb = threading.Event()

    def _kill():
        timed_out.set()
        if proc.poll() is None:
            proc.terminate()

    def _heartbeat():
        while not stop_hb.wait(heartbeat_sec):
            if proc.poll() is None:
                elapsed = int(time.monotonic() - start)
                print(f"[{label}][{time.strftime('%H:%M:%S')}] 仍在运行… 已等待 {elapsed}s", flush=True)
            else:
                return

    timer = threading.Timer(timeout_sec, _kill)
    timer.start()
    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()
    rc = -1
    try:
        if proc.stdout is None:
            rc = proc.wait()
        else:
            for line in proc.stdout:
                sys.stdout.write(f"[{label}] {line}")
                sys.stdout.flush()
            rc = proc.wait()
    finally:
        timer.cancel()
        stop_hb.set()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        rc = proc.returncode if proc.returncode is not None else -1
        _active_proc = None

    elapsed = int(time.monotonic() - start)
    if timed_out.is_set():
        print(
            f"\n[{label}][{time.strftime('%H:%M:%S')}] 达到 {timeout_sec}s 超时（实际 {elapsed}s），"
            f"已终止。可重跑以继续。",
            file=sys.stderr,
        )
        return -1
    print(f"[{label}][{time.strftime('%H:%M:%S')}] 结束 rc={rc} 耗时 {elapsed}s", flush=True)
    return rc


# ---------------------- 入口 ----------------------
@dataclass
class RunnerConfig:
    target: Path
    driver: WorkflowDriver
    workflow_config: dict            # 透传给 driver

    claude_cmd: str = CLAUDE_CMD
    timeout_min: int = DEFAULT_TIMEOUT_MIN
    heartbeat_sec: int = DEFAULT_HEARTBEAT_SEC
    permission_mode: str = DEFAULT_PERMISSION
    no_session_persistence: bool = True
    log_path: Path = Path(".ab-review/run.log")

    force_install: bool = False
    assume_yes: bool = False
    dry_run: bool = False
    install_only: bool = False        # 只装 skill，不跑工作流
    reset_only: bool = False          # 只跑 driver.init(reset=True)，不进 while 循环


def _ensure_skills(driver: WorkflowDriver, *, force: bool, assume_yes: bool) -> dict[str, str]:
    """按 ``driver.required_skills()`` 装 skill —— 单一可信源。

    **不要**按 ``target`` 的 object_type / doc_class 过滤；少装会断
    skill-to-skill dispatch（ab-review 运行时 invoke rtl-analyze 做交叉分析，
    找不到就静默失败）。target 分类仅供 pre-check（找配套 RTL 源 / 阻塞判定）
    使用，与 install 决策完全解耦。

    Review 标记 F-9 提议按 object_type 动态过滤，**已拒绝**：理由见
    PROGRESS.md "安装层单一可信源原则"。
    """
    results: dict[str, str] = {}
    for skill in driver.required_skills():
        results[skill] = _skills_runtime.install(
            skill, force=force, assume_yes=assume_yes, out=sys.stderr,
        )
    return results


def run(cfg: RunnerConfig) -> int:
    """主入口。返回进程退出码（0 = 成功 / 自然结束）。"""

    # 0) 信号处理
    signal.signal(signal.SIGINT, _sigint_handler)

    # 1) skill 安装
    install_results = _ensure_skills(
        cfg.driver, force=cfg.force_install, assume_yes=cfg.assume_yes
    )
    if any(v == "error" for v in install_results.values()):
        print("[runner] skill 安装失败，退出", file=sys.stderr)
        return 2

    if cfg.install_only:
        for name, status in install_results.items():
            print(f"  - {name}: {status}")
        return 0

    # 2) 日志
    _setup_logging(cfg.log_path)

    # 3) 驱动初始化
    try:
        state = cfg.driver.init(cfg.target, cfg.workflow_config)
    except RuntimeError as e:
        # F-7：driver raise RuntimeError（如 pre-check 用户主动 abort）→ rc=2
        print(f"[runner] driver.init 主动中止: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[runner] driver.init 失败: {e}", file=sys.stderr)
        return 3
    print(f"[runner] driver={cfg.driver.name} target={cfg.target} state={state}")

    # 3.5) reset-only：跑完 init 就退
    if cfg.reset_only:
        print("[runner] reset 完成，退出")
        return 0

    # 4) dry-run 预览
    if cfg.dry_run:
        print("\n[dry-run] 以下流程不会实际执行 claude：")
        print(f"  driver: {cfg.driver.name}")
        print(f"  state:  {state}")
        sim_state = dict(state)
        preview_step = 0
        max_preview = 64  # 防御上限
        while preview_step < max_preview:
            if cfg.driver.is_done(sim_state):
                break
            step = cfg.driver.next_step(sim_state, cfg.workflow_config)
            if step is None:
                break
            preview_step += 1
            cmd = _build_cmd(step, cfg.claude_cmd, cfg.permission_mode, cfg.no_session_persistence)
            print(f"  步骤 {preview_step}: role={step.role} model={step.model} "
                  f"settings={step.settings}")
            print(f"    cmd: {' '.join(shlex.quote(c) for c in cmd)}")
            sim_state = cfg.driver.advance_for_preview(sim_state, step)
        return 0

    # 5) 主循环
    step_no = 0
    while True:
        # 重读 state（防止 step 内 skill 自己更新了 state.json）
        state = cfg.driver.refresh(cfg.target, cfg.workflow_config)
        if cfg.driver.is_done(state):
            print("\n" + "=" * 64)
            print(f"{cfg.driver.name} 工作流结束")
            print("=" * 64)
            for k, v in state.items():
                print(f"  {k}: {v}")
            return 0

        step = cfg.driver.next_step(state, cfg.workflow_config)
        if step is None:
            print("[runner] driver.next_step 返回 None 且未标记 done，按结束处理", file=sys.stderr)
            return 0

        step_no += 1
        label = step.label or f"{cfg.driver.name}-{step.role}"
        cmd = _build_cmd(step, cfg.claude_cmd, cfg.permission_mode, cfg.no_session_persistence)
        timeout_sec = cfg.timeout_min * 60
        print(f"\n[步骤 {step_no}] {label} → role={step.role} model={step.model}")
        rc = _stream_claude(
            cmd, label, timeout_sec, cfg.heartbeat_sec,
            cwd=step.cwd, extra_env=step.extra_env,
        )
        # F-1：通知 driver 本步完成（single_skill 用它写 step_count=1，ab_review 默认 no-op）
        # 不在 rc != 0 时调 —— 失败留给用户决定是否 --reset 重跑，不让 driver 推进 state
        if rc == 0:
            try:
                cfg.driver.on_step_finished(state, step, {"rc": rc})
            except Exception as e:
                print(f"[runner] on_step_finished 异常（不影响本轮结果）：{e}", file=sys.stderr)
        if rc != 0:
            print(f"\n[runner] {label} 进程退出码 {rc}，暂停。可重跑以继续。", file=sys.stderr)
            return rc if rc > 0 else 1

    # 不可达


__all__ = ["RunnerConfig", "run", "_stream_claude", "_build_cmd"]