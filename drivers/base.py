"""WorkflowDriver / Step —— 所有 workflow 驱动的抽象基类。

新加 workflow（如 abc-review / rtl-analyze / cpp-analyze）只需：
1. 继承 ``WorkflowDriver``。
2. 在 ``next_step`` 里返回 ``Step``，runner 负责用 ``claude -p`` 调度。
3. ``required_skills`` 列出要保证已安装的 skill 名（runner 会调 installer）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Step:
    """runner 一次调度所需的全部信息。"""

    role: str                       # 角色标签：'B' / 'A' / 'analyzer' / …
    prompt: str                     # 完整 prompt，通常是 ``/<skill> ...``
    model: str | None = None        # 显式指定模型；None 时由 claude CLI 默认
    settings: Path | None = None    # --settings 指定的 json
    cwd: Path | None = None         # claude -p 运行时的工作目录；None 用当前
    label: str | None = None        # 进度展示用；缺省回退到 role
    extra_env: dict[str, str] = field(default_factory=dict)


class WorkflowDriver(ABC):
    """所有工作流驱动的统一接口。"""

    name: str = "abstract"

    @abstractmethod
    def required_skills(self) -> list[str]:
        """返回本驱动需要的 skill 名列表；runner 会先确保它们已安装。"""

    @abstractmethod
    def init(self, target: Path, config: dict) -> dict:
        """初始化或恢复 state，返回 ``state`` 字典。

        失败应 raise，让 runner 报错退出。
        """

    @abstractmethod
    def next_step(self, state: dict, config: dict) -> Step | None:
        """根据当前 state 计算下一步；返回 ``None`` 表示工作流已结束。"""

    @abstractmethod
    def is_done(self, state: dict) -> bool:
        """终止条件判定（独立于 ``next_step`` 的 ``None``，方便重入）。"""

    # F-9: 删 label 抽象方法 —— runner 实际用 step.label / step.role，没调用过
    # driver.label(state)。如未来真要展示用 step.label / step.role 已够。

    # ---- 默认实现 ----
    def refresh(self, target: Path, config: dict) -> dict:
        """每轮结束后由 runner 调用以拉取最新 state。

        默认等价于 ``init``：多数 driver 的 init 在 state 已存在时是
        "show"，无副作用。driver 可覆写以提供更廉价的刷新路径。
        """
        return self.init(target, config)

    def advance_for_preview(self, state: dict, step: Step) -> dict:
        """dry-run 模式专用：返回 ``state`` 模拟执行完 ``step`` 之后的样子。

        默认 ``raise NotImplementedError`` —— 子类忘覆写会让 dry-run 死循环，
        不如早爆。driver 应基于自身的 state 推进语义覆写：ab-review 切
        turn/round，single_skill 增 step_count。
        """
        raise NotImplementedError(
            f"{type(self).__name__} 必须覆写 advance_for_preview（不覆写会让 dry-run 死循环）"
        )

    def on_step_finished(self, state: dict, step: Step, result: dict) -> None:
        """runner 跑完一步后回调；多数 driver 不需要。"""


__all__ = ["Step", "WorkflowDriver"]