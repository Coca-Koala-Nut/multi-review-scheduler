# multi-review-scheduler 进度存档

## 当前状态（2026-06-26 → 2026-06-27）

- 重构为 skill 工作流调度框架 + skill 独立 PyPI 包。
- 完成 F-1..F-14 全量 review（除 F-9 拒绝外），P0/P1/P2 全部落地。
- 跑真实 case 暴露两个 hotfix：pre-check 搜索深度 8 → 15；settings 路径 `~` 透传 expanduser。
- USER_GUIDE.md 全面更新；原始重构计划 `multi_review_scheduler_plan.md` 已删（9 步全做完）。
- Doc sweep：README 字段列表补 precheck_max_depth；ab-review SKILL.md paired-code 格式补 max_depth 行。
- Round-2 review：15 条 finding 评估，14 成立 + 1 已闭环，全部落地。
- 工程重命名：`multi_review_scheduler_m3/` → `multi_review_scheduler/`。
- Git 上传流程闭环：`.gitignore` + `.githooks/pre-commit` 防回退。
- 回归通过：CLI 加载 / argparse None 默认 / config_io roundtrip / extract_stems body 抽取 /
  find_project_root cwd 优先 / TUI fail-fast / pre-check 候选搜索 / engine/installer.py shim 删除无回归。

## F-X review 处理总结

| ID | 标题 | 处理 |
|---|---|---|
| F-1 | init() 死代码 | ✅ 删 |
| F-2 | argparse default magic number | ✅ 改 None + config 兜底 |
| F-3 | TUI 自动跑 + 自动 pip | ✅ fail-fast + save-only exit 0，不加 --ui-run |
| F-4 | pre-check 仅 LLM 守纪律 | ✅ 脚本层 input("[y/n/p]") + CODE_MISSING.md |
| F-5 | project_root 检测策略 | ✅ 选 A：cwd 优先 + fallback 上溯 |
| F-6 | extract_stems 只看文件名 | ✅ 读 body 抽 PascalCase/snake_case 模块名 |
| F-7 | paired-code 写文件 vs 注入 prompt | ✅ 双管齐下 |
| F-8 | advance_for_preview 默认死循环 | ✅ 改 raise NotImplementedError |
| F-9 | required_skills 按 object_type 过滤 | ❌ **拒绝** — driver.required_skills() 是单一可信源 |
| F-10 | skill 包 fallback 文档 | ✅ README 重写 |
| F-11 | __import__('sys').stderr | ✅ 改 sys.stderr（顶部已 import） |
| F-12 | engine/installer.py 兼容 shim | ✅ 删除（无外部引用） |
| F-13 | find_config 用默认值启发 | ✅ 改 tomlkit 解析 [tool.mrs] section 直接判定 |
| F-14 | pyproject.toml 残留 [tool.mrs] | ✅ 删段 + 建 mrs.example.toml |

## 安装层单一可信源原则

**Install 决策 = driver.required_skills()。绝不按 target object_type / doc_class 过滤。**

理由：
1. ab-review 运行时可能主动 invoke rtl-analyze 做交叉分析，少装 → 调不动
2. classify_target() 靠文件名启发式不可靠（tutorial_about_rtl.md 漏判）
3. 两套分类打架 → 单一可信源避免回退

代码固化位置：`engine/runner.py::_ensure_skills` 顶部 docstring。

## 继续工作的命令

```bash
# 装
pip install -e .
pip install -e ./skills/ab-review
pip install -e ./skills/rtl-analyze

# 跑
multi-review-scheduler --target CordicVect_analysis.md \
  --settings-b ~/.claude/settings-db-kimi.json \
  --settings-a ~/.claude/settings-ds.json --max-rounds 3
```