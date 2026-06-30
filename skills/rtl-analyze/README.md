# mrs-skill-rtl-analyze

`rtl-analyze` skill for [`multi-review-scheduler`](https://pypi.org/project/multi-review-scheduler/)。

RTL 代码评审/分析/逆向文档。

## 安装

```bash
# 与主包一起装
pip install multi-review-scheduler[rtl]

# 单独装
pip install mrs-skill-rtl-analyze
```

## 用法

```bash
multi-review-scheduler --workflow rtl-analyze --target rtl/top.sv \
  --settings ~/.claude/settings.json
```

## 依赖

- `multi-review-scheduler` 主包