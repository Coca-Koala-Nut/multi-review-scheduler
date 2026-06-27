#!/usr/bin/env bash
# Pre-commit hook：阻止 [tool.mrs] 段误提交到 pyproject.toml
#
# 用户跑 `multi-review-scheduler --ui` 后，pyproject.toml 末尾会被自动追加
# [tool.mrs] 段（存用户本地的 default_target / settings_b/a 等）。这是用户
# 本地状态，不应该污染源仓库（见 review F-14）。
#
# 启用：
#   git config core.hooksPath .githooks
#
# 跳过（紧急情况）：
#   git commit --no-verify

set -e

# 检查本次 commit 是否包含 pyproject.toml
if ! git diff --cached --name-only | grep -q "^pyproject.toml$"; then
    exit 0
fi

# 检查 staged 的 pyproject.toml 是否含 [tool.mrs]
if git show ":pyproject.toml" | grep -q "^\[tool\.mrs\]"; then
    cat <<'EOF' >&2
❌ pyproject.toml 含 [tool.mrs] 段（用户本地配置，不能提交）

   [tool.mrs] 段存的是用户本地的 default_target / settings_b/a 等，
   跟源仓库无关。提交它会污染分发包（review F-14 想避免的）。

   修复（提交前 strip）：
     python3 -c "
     import re, pathlib
     p = pathlib.Path('pyproject.toml')
     text = p.read_text()
     new = re.sub(r'\n\[tool\.mrs\][^\[]*', '', text, flags=re.DOTALL)
     p.write_text(new)
     print('stripped')
     "
     git add pyproject.toml

   紧急跳过：git commit --no-verify
EOF
    exit 1
fi