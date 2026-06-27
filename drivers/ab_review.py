"""A/B 多轮审阅工作流驱动。

兼容旧 ``multi_review_scheduler.py`` 的行为，但只负责 state 推进与下一步
prompt 生成。子进程调度 / 心跳 / 超时 / 日志交给 ``engine.runner``。

约定（与旧脚本一致）：
- state 由 ``ab-review`` skill 提供的 ``_ab_state.py`` 管理。
- B 角色 prompt: ``/ab-review <target> --split --role b [b_extra]``
- A 角色 prompt: ``/ab-review <target> --split --role a [a_extra]``
- verdict 非空或 ``turn == "done"`` 表示终止。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .base import Step, WorkflowDriver

DEFAULT_STATE_SCRIPT = (
    Path(os.environ.get("MRS_STATE_SCRIPT"))
    if os.environ.get("MRS_STATE_SCRIPT")
    else Path.home() / ".claude/skills/ab-review/scripts/_ab_state.py"
)

EXT_TO_TYPE = {
    ".md": "doc", ".markdown": "doc", ".txt": "doc",
    ".v": "rtl", ".sv": "rtl", ".vhd": "rtl", ".vhdl": "rtl",
}

RTL_KEYS = ("module", "endmodule", "always_ff", "always @", "entity", "architecture")
DOC_KEYS = ("## ", "# ", "```")

# F-2: --doc-class CLI 枚举（auto / with-code / standalone）→ 内部分类值
# （rtl / doc-with-code / standalone-doc / unknown-doc）归一化。
# 不归一化会导致：
#   --doc-class with-code  → cls="with-code" 不在阻塞集合 → 缺代码不阻塞
#   --doc-class standalone → cls="standalone" 不等于 "standalone-doc" → 照样搜代码
_DOC_CLASS_NORMALIZE = {
    "auto": None,           # 不覆盖 classify_target
    "with-code": "doc-with-code",
    "standalone": "standalone-doc",
}


def _run_state(state_script: Path, args: list[str]) -> dict:
    """调用 ``_ab_state.py``，返回原始 dict。

    兼容两种返回格式：
    - ``init``  返回 ``{"state": {...}, "created": bool}``
    - ``show``/``reset`` 直接返回 state dict
    """
    cmd = [sys.executable, str(state_script)] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(
            f"_ab_state.py {' '.join(str(a) for a in args)} 失败:\n"
            f"stdout={r.stdout}\nstderr={r.stderr}"
        )
    return json.loads(r.stdout)


def _unwrap(out: dict) -> dict:
    """``init`` 的返回带 ``state`` 包装；``show`` 是裸 dict。统一为 state。"""
    if isinstance(out, dict) and "state" in out and isinstance(out["state"], dict):
        return out["state"]
    return out


def _infer_object_type(target: Path) -> str:
    ext = target.suffix.lower()
    t = EXT_TO_TYPE.get(ext)
    if t:
        return t
    try:
        head = "\n".join(target.read_text(encoding="utf-8", errors="ignore").splitlines()[:50])
    except OSError:
        head = ""
    if any(k in head for k in RTL_KEYS):
        return "rtl"
    if any(k in head for k in DOC_KEYS) or head.count("\n") >= 3:
        return "doc"
    try:
        while True:
            t = input(f"无法从扩展名推断 {target} 的对象类型，请输入 doc 或 rtl: ").strip().lower()
            if t in ("doc", "rtl"):
                return t
            print("无效输入，请重试。")
    except (EOFError, KeyboardInterrupt):
        # F-5：CI / 管道 / --dry-run 重定向下 input() 抛 EOFError，
        # 不接住会冒泡到 runner 顶层 → rc=3 退出，无友好提示
        print(f"[ab-review] 非 TTY 环境且无法推断 {target} 的 object_type，按 doc 处理",
              file=sys.stderr)
        return "doc"


class ABReviewDriver(WorkflowDriver):
    """A/B 多轮审阅 driver。

    ``config`` 字典支持的键：
    - target: Path（必填）
    - state_file: Path（默认 .ab-review/state.json）
    - state_script: Path（默认 ~/.claude/skills/ab-review/scripts/_ab_state.py）
    - reset: bool（先 reset 再初始化）
    - max_rounds: int（默认 3）
    - range: str | None
    - object_type: "doc" | "rtl" | None（None 时按扩展名/内容启发）
    - model_b / model_a: str | None
    - settings_b / settings_a: str | None
    - b_extra / a_extra: str | None（附加到 prompt 后）
    """

    name = "ab-review"

    def __init__(self) -> None:
        self._state_script: Path | None = None

    # ---- 路径工具 ----
    def _script(self, config: dict) -> Path:
        if self._state_script is None:
            self._state_script = Path(config.get("state_script") or DEFAULT_STATE_SCRIPT)
        return self._state_script

    def _state_file(self, config: dict) -> Path:
        return Path(config.get("state_file", ".ab-review/state.json"))

    def _run(self, config: dict, *args: str) -> dict:
        return _run_state(self._script(config), list(args))

    def _run_unwrap(self, config: dict, *args: str) -> dict:
        return _unwrap(self._run(config, *args))

    # ---- WorkflowDriver ----
    def required_skills(self) -> list[str]:
        # ab-review 在审阅 RTL 对象时可能内嵌调用 rtl-analyze，统一打包进来。
        # 文档对象下也会装 rtl-analyze（多占 200KB），换取"装一次就齐"的不变量。
        return ["ab-review", "rtl-analyze"]

    def init(self, target: Path, config: dict) -> dict:
        # 1) 可选 reset —— reset 后立即短路返回，不走 infer/init
        if config.get("reset"):
            self._run(config, "reset")
            sf = self._state_file(config)
            if sf.exists():
                return self._run_unwrap(config, "show")
            # reset 后没 state_file（CLI 早返回用）：返回占位 state
            return {
                "target": str(target),
                "turn": "b",
                "round": 1,
                "max_rounds": int(config.get("max_rounds", 3)),
                "verdict": None,
                "object_type": config.get("object_type") or "doc",
                "mode": "split",
            }

        # 2) 已有 state → show（注意：target 变了或 paired-code.md 不存在时重做 pre-check）
        sf = self._state_file(config)
        if sf.exists():
            state = self._run_unwrap(config, "show")
            need_precheck = (not (sf.parent / "paired-code.md").exists()) \
                or (state.get("target") != str(target))
            if need_precheck:
                self._maybe_pair_code(target, state, config)
            # 保护：旧 state 来自别的 target / 已完成（verdict 非空 或 turn=done）
            # 不一致时自动 reset，避免小白被旧 state 误导（"工作流结束"但其实没跑）
            state_target = state.get("target", "")
            cur_target = str(target)
            if state_target and state_target != cur_target:
                print(f"[ab-review] 旧 state 来自 {state_target}，与当前 target {cur_target} 不一致 → 自动 reset",
                      file=sys.stderr)
                self._run(config, "reset")
                # 走 init 重新建 state
            elif not config.get("resume") and (state.get("verdict") is not None or state.get("turn") == "done"):
                # 同 target 但已结束 → 自动 reset 重新跑
                print(f"[ab-review] 检测到 {cur_target} 的 state 已完成（verdict={state.get('verdict')!r}），自动 reset 重新跑",
                      file=sys.stderr)
                self._run(config, "reset")
            else:
                return state

        # 3) 否则 init
        object_type = config.get("object_type") or _infer_object_type(target)
        max_rounds = int(config.get("max_rounds", 3))
        args = [
            "init", str(target),
            "--object-type", object_type,
            "--max-rounds", str(max_rounds),
        ]
        if config.get("range"):
            args += ["--range", str(config["range"])]
        state = self._run_unwrap(config, *args)

        # 4) pre-check：object_type=doc 时找配套 RTL 源
        self._maybe_pair_code(target, state, config)
        return state

    def _maybe_pair_code(self, target: Path, state: dict, config: dict) -> None:
        """按 target 分类决定配对策略：

        - ``doc-with-code`` / ``unknown-doc``：找 RTL 源候选 → ``paired-code.md``
          找不到时写 ``CODE_MISSING.md`` 并在 TTY 下 ``input("[y/n/p]")`` 阻塞。
          非 TTY（CI / 脚本调用）下写告警到 stderr 但不阻塞。
        - ``standalone-doc``：跳过（写最小占位，B 角色直接审）
        - ``rtl``：不适用（审代码走 rtl-analyze，不写此文件）

        SKILL.md 协议 + 脚本层双保险：协议靠 LLM 守纪律，脚本层做硬阻塞兜底。
        """
        try:
            from ._project import classify_target, find_project_root, search_project, extract_stems
        except ImportError:
            return
        if state.get("object_type") != "doc":
            return
        sf = self._state_file(config)
        out = sf.parent / "paired-code.md"
        try:
            # CLI / config 显式覆盖优先（归一化映射，见 _DOC_CLASS_NORMALIZE）
            raw = config.get("doc_class") or classify_target(target)
            cls = _DOC_CLASS_NORMALIZE.get(raw, raw)  # raw 已是分类值时原样
            project_root = Path(config["project_root"]) if config.get("project_root") \
                else find_project_root(target.parent)
            max_depth = int(config.get("precheck_max_depth") or 15)

            if cls == "standalone-doc":
                # 自包含文档：不配对；写 N/A 占位
                lines = [
                    "# 配套 RTL 源",
                    "",
                    f"- target : {target}",
                    f"- project_root : {project_root}",
                    f"- max_depth : N/A (standalone doc)",
                    "- doc_class : standalone-doc",
                    "- found_by : n/a",
                    "- candidates :",
                    "  - N/A (standalone doc — 无需配套代码)",
                ]
                sf.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return

            # doc-with-code / unknown-doc：找 RTL 候选
            stems = extract_stems(target)
            candidates: list[Path] = []
            for stem in stems:
                for ext in (".v", ".sv", ".bak", ".vhd", ".vhdl", ".svh"):
                    candidates.extend(search_project(
                        project_root, [f"**/{stem}*{ext}"], max_depth=max_depth,
                    ))
            target_resolved = target.resolve()
            candidates = [c for c in candidates if c.resolve() != target_resolved]
            seen: set[Path] = set()
            uniq: list[Path] = []
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    uniq.append(c)
            candidates = uniq

            lines = [
                "# 配套 RTL 源",
                "",
                f"- target : {target}",
                f"- project_root : {project_root}",
                f"- max_depth : {max_depth}",
                f"- doc_class : {cls}",
                f"- found_by : {'doc-reference' if candidates else 'none'}",
                "- candidates :",
            ]
            for c in candidates:
                lines.append(f"  - {c}")
            if not candidates:
                lines.append("  - 无")
            sf.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # 强制阻塞：doc-with-code 找不到 RTL 候选时
            if not candidates and cls in ("doc-with-code", "unknown-doc"):
                # RuntimeError（用户主动中止 / 非 TTY 默认中止）必须向外冒泡
                self._block_missing_code(target, project_root, stems, config)
        except RuntimeError:
            # 用户主动中止 / 非 TTY 默认中止 —— 让 runner 统一接住（rc=2）
            raise
        except Exception as e:
            # 其他 pre-check 异常不影响主流程；只记一行 hint
            print(f"[ab-review] paired-code.md 生成失败（不阻塞）: {e}",
                  file=sys.stderr)

    def _block_missing_code(
        self, target: Path, project_root: Path, stems: list[str], config: dict,
    ) -> None:
        """doc-with-code 但找不到 RTL 候选时：写 CODE_MISSING.md + TTY 阻塞。

        TTY：``input("[y/n/p]")`` 让用户决定 continue / skip / abort
        非 TTY（CI / pipe）：stderr 一行警告 + 继续（不阻塞自动化）
        ``--no-precheck-block`` 显式跳过阻塞（Power user）
        """
        if config.get("no_precheck_block"):
            return
        sf = self._state_file(config)
        code_missing = sf.parent / "CODE_MISSING.md"
        max_depth = int(config.get("precheck_max_depth") or 15)
        lines = [
            "# 配套 RTL 源缺失",
            "",
            f"- target : {target}",
            f"- project_root : {project_root}",
            f"- max_depth : {max_depth}",
            f"- stems 抽自文件名: {stems}",
            "- 搜索范围: 全工程根（已排除 .git / __pycache__ / node_modules / "
            ".ab-review / .workflow / .venv / *.egg-info / dist / build）",
            "- 找不到的原因可能是：",
            "  - 模块名拼写与 .v/.sv 文件名不一致",
            "  - RTL 源在另一个 repo",
            f"  - **路径深度超过 {max_depth}**（SoC IP 经常深达 9-12 层），用 "
            "`--precheck-max-depth 20` 或 [tool.mrs].precheck_max_depth 加大",
            "  - 工程根识别错误（用 --project-root 显式覆盖）",
            "",
            "下一步：",
            "  - 检查 target 文件里写的模块名是否正确",
            "  - 用 --project-root 显式指定 RTL 所在目录",
            "  - 用 --precheck-max-depth N 加大搜索深度",
            "  - 或用 --doc-class standalone 声明此文档无需配套代码",
            "  - 或 --no-precheck-block 跳过阻塞（Power user）",
        ]
        sf.parent.mkdir(parents=True, exist_ok=True)
        code_missing.write_text("\n".join(lines) + "\n", encoding="utf-8")

        if not sys.stderr.isatty():
            # F-11：非 TTY 默认中止（评审失真 = 应当失败，不应静默继续）
            # 显式跳过用 --no-precheck-block
            print(
                f"[ab-review] ❌ doc-with-code 目标 {target} 在 {project_root} 下未找到配套 RTL 源"
                f"（max_depth={max_depth}）。已写 {code_missing}。\n"
                f"非 TTY 环境无法交互确认，默认中止。\n"
                f"  跳过阻塞：--no-precheck-block\n"
                f"  重新跑：multi-review-scheduler --target {target} --project-root {project_root}",
                file=sys.stderr,
            )
            raise RuntimeError(
                f"pre-check failed: doc-with-code {target} 无 RTL 源 (非 TTY 默认中止)"
            )

        # TTY：阻塞等用户决定
        try:
            while True:
                ans = input(
                    f"\n[ab-review] {target} 是 doc-with-code 但 {project_root} 下未找到 RTL 源"
                    f"（max_depth={max_depth}）。\n"
                    f"  [y] 继续审（无 RTL 上下文）  [n] 中止  [p] 打印搜索结果详情\n> "
                ).strip().lower()
                if ans in ("y", "yes", "continue"):
                    print("[ab-review] 用户选择继续（无 RTL 上下文）", file=sys.stderr)
                    return
                if ans in ("n", "no", "abort"):
                    print("[ab-review] 用户中止。请修正 target / project_root / doc-class 后重跑。",
                          file=sys.stderr)
                    # F-7: driver 不直接 sys.exit —— 越层。raise RuntimeError 让 runner 统一处理退出码
                    raise RuntimeError("user aborted in pre-check (n)")
                if ans in ("p", "print"):
                    print(f"  target={target}\n  project_root={project_root}\n"
                          f"  stems={stems}\n  max_depth={max_depth}",
                          file=sys.stderr)
                    continue
                print("  无效输入；y=继续 / n=中止 / p=打印详情")
        except (EOFError, KeyboardInterrupt):
            print("\n[ab-review] 输入中断，按中止处理。", file=sys.stderr)
            raise RuntimeError("pre-check aborted by user (Ctrl+C / EOF)")

    def next_step(self, state: dict, config: dict) -> Step | None:
        turn = state.get("turn")
        if turn not in ("a", "b"):
            return None
        target = config["target"]
        prompt = f"/ab-review {target} --split --role {turn}"
        if turn == "b" and config.get("b_extra"):
            prompt += f" {config['b_extra']}"
        if turn == "a" and config.get("a_extra"):
            prompt += f" {config['a_extra']}"

        # F-7 双管齐下：写 .ab-review/paired-code.md（已做）+ 把 candidates 摘要注入 prompt
        # 让 B/A 角色直接看到，无需再读一次文件
        paired_hint = self._read_paired_candidates(config)
        if paired_hint:
            prompt += f"\n\n<!-- paired-code candidates: {paired_hint} -->"

        return Step(
            role=turn.upper(),
            prompt=prompt,
            model=config.get(f"model_{turn}"),
            settings=Path(config[f"settings_{turn}"]) if config.get(f"settings_{turn}") else None,
            label=f"B-round-{state.get('round', '?')}" if turn == "b"
                  else f"A-round-{state.get('round', '?')}",
        )

    def _read_paired_candidates(self, config: dict) -> str:
        """从 .ab-review/paired-code.md 抽 candidates section，截前 5 条。

        返回字符串供注入 prompt HTML 注释；失败 / 文件不存在 → 空串（不阻塞）。
        """
        try:
            sf = self._state_file(config)
            paired = sf.parent / "paired-code.md"
            if not paired.exists():
                return ""
            text = paired.read_text(encoding="utf-8", errors="ignore")
            # 找 "- candidates :" 段到下个 "- " 段或文件末尾
            in_candidates = False
            items: list[str] = []
            for line in text.splitlines():
                if line.strip().startswith("- candidates"):
                    in_candidates = True
                    continue
                if in_candidates:
                    if line.startswith("- ") and not line.startswith("  -"):
                        break  # 下一段
                    s = line.strip().lstrip("-").strip()
                    if s and s != "无":
                        items.append(s)
                if len(items) >= 5:
                    break
            return "; ".join(items) if items else ""
        except Exception:
            return ""

    def is_done(self, state: dict) -> bool:
        return state.get("verdict") is not None or state.get("turn") == "done"

    # F-9: label(state) 删除 —— runner 用 step.label / step.role，不调 driver.label

    def advance_for_preview(self, state: dict, step: Step) -> dict:
        """dry-run 模拟：a↔b，b 之后 round+1。"""
        sim = dict(state)
        if sim.get("turn") == "b":
            sim["turn"] = "a"
        else:
            cur = int(sim.get("round", 1))
            sim["turn"] = "b"
            sim["round"] = cur + 1
            max_rounds = int(sim.get("max_rounds") or 0)
            if max_rounds and cur + 1 > max_rounds:
                sim["verdict"] = "max-rounds-reached"
        return sim


__all__ = ["ABReviewDriver", "DEFAULT_STATE_SCRIPT"]