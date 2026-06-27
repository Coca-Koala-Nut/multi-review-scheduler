"""单次 skill 驱动：跑一次 ``/<skill> <target>`` 即结束。

适用于 ``rtl-analyze`` / ``cpp-analyze`` / ``python-analyze`` 等只需要
一次性分析的工作流。state 落盘到 ``.workflow/<skill>.json``，方便
``--resume`` 或事后查证。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .base import Step, WorkflowDriver


class SingleSkillDriver(WorkflowDriver):
    """单次 skill 调用的 driver。"""

    def __init__(self, workflow: str) -> None:
        self.workflow = workflow
        self._state_file: Path | None = None

    def required_skills(self) -> list[str]:
        return [self.workflow]

    def _default_state_file(self, config: dict) -> Path:
        return Path(config.get("state_file", f".workflow/{self.workflow}.json"))

    def init(self, target: Path, config: dict) -> dict:
        sf = self._default_state_file(config)
        self._state_file = sf
        sf.parent.mkdir(parents=True, exist_ok=True)
        if sf.exists():
            try:
                state = json.loads(sf.read_text(encoding="utf-8"))
                # 已 resume 时：paired-context.md 不存在 或 target 变了 → 重做
                need_precheck = (not (sf.parent / "paired-context.md").exists()) \
                    or (state.get("target") != str(target))
                if need_precheck:
                    self._maybe_pair_context(target, state, config)
                return state
            except (json.JSONDecodeError, OSError):
                pass  # 损坏则重写
        state = {
            "workflow": self.workflow,
            "target": str(target),
            "started_at": time.time(),
            "step_count": 0,
        }
        sf.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        self._maybe_pair_context(target, state, config)
        return state

    def _maybe_pair_context(self, target: Path, state: dict, config: dict) -> None:
        """按 target 分类决定配对策略：

        - ``rtl``：找关联代码 + 关联文档（建议级别，找不到仅提醒）
        - 其他（doc / standalone-doc 等）：跳过；single_skill 主要服务 rtl 分析

        找不到时仅打印提醒、不阻塞；产物 ``.workflow/paired-context.md`` 记录
        found_by / candidates，让 LLM 据此决定要不要扩大搜索。
        """
        try:
            from ._project import classify_target, find_project_root, search_project, extract_stems
        except ImportError:
            return
        try:
            cls = config.get("doc_class") or classify_target(target)
            if cls != "rtl":
                # rtl 之外的 target 不配对；single_skill 主要是 rtl-analyze
                return
            project_root = Path(config["project_root"]) if config.get("project_root") \
                else find_project_root(target.parent)
            stems = extract_stems(target)
            related_code: list[Path] = []
            for stem in stems:
                for ext in (".v", ".sv", ".bak", ".vhd", ".vhdl", ".svh"):
                    related_code.extend(search_project(project_root, [f"**/{stem}*{ext}"]))
            related_docs: list[Path] = []
            for stem in stems:
                for pat in (f"**/{stem}*.md", f"**/{stem}_*.md", f"**/*_{stem}.md"):
                    related_docs.extend(search_project(project_root, [pat]))
            # 排除 target 自身
            target_resolved = target.resolve()
            related_docs = [d for d in related_docs if d.resolve() != target_resolved]

            def _dedup(seq: list[Path]) -> list[Path]:
                seen: set[Path] = set()
                out: list[Path] = []
                for p in seq:
                    if p not in seen:
                        seen.add(p)
                        out.append(p)
                return out
            related_code = _dedup(related_code)
            related_docs = _dedup(related_docs)

            out_path = (self._state_file or self._default_state_file(config)).parent / "paired-context.md"
            lines = [
                "# 配套上下文（rtl-analyze）",
                "",
                f"- target : {target}",
                f"- project_root : {project_root}",
                "- related_code :",
            ]
            for c in related_code:
                lines.append(f"  - {c}")
            if not related_code:
                lines.append("  - 无")
            lines.append("- related_docs :")
            for d in related_docs:
                lines.append(f"  - {d}")
            if not related_docs:
                lines.append("  - 无")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            # 提醒：仅"无"项打印
            if not related_code and not related_docs:
                print(f"ℹ 提醒：未找到关联代码和关联文档（stem={stems}，工程根={project_root}），将基于代码自身审阅")
            elif not related_code:
                print(f"ℹ 提醒：未找到关联代码（stem={stems}），将基于代码自身审阅")
            elif not related_docs:
                print(f"ℹ 提醒：未找到关联文档（stem={stems}），将基于代码自身审阅")
        except Exception as e:
            print(f"[single_skill] paired-context.md 生成失败（不阻塞）: {e}",
                  file=__import__("sys").stderr)

    def refresh(self, target: Path, config: dict) -> dict:
        sf = self._state_file or self._default_state_file(config)
        if sf.exists():
            try:
                return json.loads(sf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"workflow": self.workflow, "target": str(target), "step_count": 0}

    def next_step(self, state: dict, config: dict) -> Step | None:
        if state.get("step_count", 0) >= 1:
            return None
        target = config["target"]
        prompt = f"/{self.workflow} {target}"
        return Step(
            role="analyzer",
            prompt=prompt,
            model=config.get("model"),
            settings=Path(config["settings"]) if config.get("settings") else None,
            label=self.workflow,
        )

    def is_done(self, state: dict) -> bool:
        return state.get("step_count", 0) >= 1

    # F-9: label(state) 删除 —— runner 用 step.label / step.role，不调 driver.label

    def advance_for_preview(self, state: dict, step: Step) -> dict:
        """dry-run 模拟：step_count + 1。"""
        sim = dict(state)
        sim["step_count"] = sim.get("step_count", 0) + 1
        return sim

    def on_step_finished(self, state: dict, step: Step, result: dict) -> None:
        """runner 跑完一步后写回 step_count=1。"""
        if self._state_file is None:
            return
        state["step_count"] = 1
        state["finished_at"] = time.time()
        state["last_result"] = result
        try:
            self._state_file.write_text(
                json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            print(f"[single_skill] 写回 state 失败: {e}", file=__import__("sys").stderr)


__all__ = ["SingleSkillDriver"]