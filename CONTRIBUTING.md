# 贡献指南

## 环境

```bash
git clone https://github.com/karl-bro/AAAvocabDictation.git
cd vocab-dictation
python -m venv .venv
# Windows: .venv\Scripts\activate ；macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

改动 schema 或动作后务必再跑一次：

```bash
python scripts/export_tool_schemas.py
git diff --exit-code schemas/    # 确保生成物与代码同步
```

## 提交前的硬性检查

1. `pytest` 全绿（当前 76 个用例）。
2. 新增动作 → 同时更新 `ACTION_SPECS`、`docs/api-reference.md`、`skill.yaml`；
   CI 会校验 `skill.yaml` 与 `ACTION_SPECS` 的动作集合一致。
3. 评分规则变更 → 同时改 `core.py`、`docs/scoring-rules.md`、`tests/test_judge.py`，
   并在 `CHANGELOG.md` 说明为何改（历史分数会漂移，需明确告知）。
4. 新增错误码 → 同步 `schemas/response.schema.json` 的 `enum` 与文档。
5. 不提交真实词库、真实答卷照片、任何个人数据；示例数据只放 `assets/sample_items.json`。

## 代码约定

- `core.py` 保持零 I/O：不得 import `openpyxl` / `reportlab` / 文件操作，否则单元测试会变慢且难隔离。
- 适配层（`cli.py` / `http_server.py` / `mcp_server.py`）只负责协议转换，业务逻辑一律下沉到 `api.py` 或下层模块。
- 面向用户的错误信息用中文（与技能目标用户一致），代码注释与命名用中英皆可但需一致。
- 可选依赖（PDF、图像）必须在模块内部延迟导入，缺失时给出安装提示而不是 ImportError 崩溃。

## 提 PR

- 一个 PR 一件事，标题写清改了什么（如 `feat: 支持按标记范围出卷`）。
- 描述里写：动机、行为变化、如何验证（命令与结果）、对既有数据/分数的影响。
- 破坏性变更（如评分口径、批次号规则）先开 issue 讨论，不要直接合并。

## 报告问题

请附：`vocabdict capabilities` 输出、复现用的最小请求 JSON、完整错误信封
（含 `error.code` 与 `error.message`）、Python 与操作系统版本。
