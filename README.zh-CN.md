# vocab-dictation · 考研生词听写闭环

**把「生词本照片 → 入库 → 出卷 → 批改 → 错题管理 → 报告」整条链做成一个可复用技能，
用一套 JSON 接口供任何大模型应用、Agent 框架或后端直接调用。**

[English](README.md) · [快速开始](docs/quickstart.md) · [接口参考](docs/api-reference.md) · [评分口径](docs/scoring-rules.md) · [集成指南](docs/integration.md)

---

## 为什么做这个

手写生词本 + 手工听写这套流程每天要重复五件事：识别手写、录入词表、挑词排版出卷、
批改手写答案、记录错在哪。市面上的“背单词 AI”通常只做第三步。

这个项目把**整条闭环**打包成一个契约稳定的技能：模型只做它擅长的事（读手写、按流程走），
剩下的判分、统计、摘帽、排版全部交给可测试的确定性代码。

## 能力一览

| 能力 | 说明 |
| --- | --- |
| 词库管理 | 单个 xlsx，四张表（使用说明/总词库/错题本/听写记录），自动编号，按 `来源+序号+英文` 去重 |
| 出卷 | 错题优先抽样 `sample`，或**全量打乱** `shuffle_all`（不补题），`seed` 可复现顺序 |
| PDF | 填空版 + 答案版，生成后自动自检（页数、题号连续、中文与答案齐全） |
| 批改 | 1 / 0.5 / 0 三档；斜杠同义词任一即对；词组漏词/多词/错序单独判定 |
| 统计 | 听写次数、正确次数、连续正确；**半对也算一次错误** |
| 错题本 | **连续 2 次满分**自动摘帽，期间任一次失分重新计数 |
| 报告 | 逐题明细、错因分布、重点词正确率、复习建议 |
| 字母提示 | 仅等号链成员（含 `=` 前主词）；同链前 n 字母相同则提示到第 n+1 个字母 |

## 结构

```
调用方（Python SDK / CLI / HTTP / MCP）
        │
        ▼
  dispatch(action, params) → 统一 JSON 信封
        │
        ├── core.py       纯逻辑判分（零 I/O，可单测）
        ├── bank.py       词库读写、抽样、统计
        ├── grading.py    预判 / 正式批改 / 摘帽
        ├── rendering.py  听写卷与报告 PDF + 自检
        └── prepare.py    答卷照片纠偏分页（可选依赖）
```

`api.py` 是唯一知道全部动作的地方，`ACTION_SPECS` 是单一事实源，
`capabilities()` 由它自动生成各协议所需的 JSON Schema——加动作不需要改四处。

## 安装

```bash
pip install "vocab-dictation[pdf]"     # openpyxl 必需；pdf extra 用于出卷/报告
# 其他 extras：[image] pillow+numpy ｜ [dev] pytest 与全部依赖
```

Python ≥ 3.9；不联网、不需要 API Key、不依赖云服务。

## 五分钟上手

```python
from vocab_dictation import VocabDictation

vd = VocabDictation("词库.xlsx")
vd.init()
vd.add_items(items, source="v.L5-p1", date="2026-11-16")

items = vd.shuffle_all(seed=2026)                  # 全量打乱，不从词库补
meta = {"批次ID": vd.next_batch_id("2026-11-16"), "日期": "2026-11-16", "范围": "v.L5 p1"}
vd.build_dictation_pdf(items, meta, outdir="out")  # → 填空版 + 答案版，自检 OK

graded = [{"词条ID": it["词条ID"], "我的答案": ans} for it, ans in zip(items, answers)]
vd.apply(graded, batch_id=meta["批次ID"], date=meta["日期"])
vd.build_report(result, "out/批改报告.pdf")
```

跑完整示例（只在系统临时目录写文件）：

```bash
python examples/01_quickstart.py      # 一条龙
python examples/02_llm_tool_call.py   # OpenAI / Anthropic 工具声明
python examples/03_http_client.py     # HTTP 往返
python examples/04_mcp_client.py      # MCP 握手
```

## 四种入口，同一种行为

```bash
vocabdict capabilities --pretty                        # 能做什么
vocabdict call --action bank.stats --bank 词库.xlsx     # 单次调用
vocabdict serve --port 8800 --bank 词库.xlsx --token T  # HTTP 服务
vocabdict mcp                                          # MCP stdio 服务
```

## 契约

请求 `{action, params, bank?}`，响应 `{ok, action, version, data, warnings, error, meta}`。
**成功和失败结构完全相同**，调用方只需判断 `ok` 与 `error.code`。

错误码可直接分支处理：`INVALID_ACTION` / `INVALID_PARAMS` / `BANK_REQUIRED` /
`BANK_NOT_FOUND` / `BANK_EXISTS` / `DUPLICATE_BATCH` / `BANK_ERROR` / `RENDER_FAILED` /
`FILE_NOT_FOUND` / `INTERNAL_ERROR`。

其中 `DUPLICATE_BATCH` 是刻意的护栏：同一批次重复批改会把听写次数与连续正确算乱，
所以默认拒绝，除非显式 `allow_duplicate: true`。

## 评分口径

| 情形 | 得分 |
| --- | --- |
| 拼写全对，或斜杠同义词任一 | **1** |
| 错 1~2 字母可辨认（3~4 字母短词只容错 1 个） | **0.5** |
| 偏差大 / 未作答 | **0** |
| 词组漏词、多词、错序 | **0** |

半对计一次错误并进错题本；连续 2 次满分摘帽。完整口径见
[docs/scoring-rules.md](docs/scoring-rules.md)。

## 仓库结构

README / SKILL.md（Agent 契约）/ skill.yaml（机器可读配置）/ pyproject.toml /
`src/vocab_dictation/`（11 个模块）/ `schemas/`（请求响应 + 两种工具声明 + 能力清单）/
`prompts/`（识别两类照片的提示词）/ `docs/` / `examples/` / `assets/sample_items.json` /
`scripts/export_tool_schemas.py` / `tests/`（76 个用例）。

## 留给模型做的事

本项目**不做 OCR**：照片由你应用里的多模态模型读，仓库只提供严格契约：

- `prompts/extract_items.md`：黑/蓝/红圈/红波浪线的识别规则、斜杠同义词算一项、
  等号链逐成员拆分且全员标链、不确定必须写进备注；
- `prompts/read_submission.md`：**逐字转写**，禁止顺手纠正拼写。

这样分工才成立：视觉留给模型，算术与记账留给代码。

## 测试

```bash
pip install -e ".[dev]"
pytest        # 76 passed
```

覆盖评分边界、去重、范围筛选、全量打乱覆盖面、摘帽生命周期、重复批次保护、
信封与全部错误码、CLI 退出码、MCP 握手、HTTP（含 401）以及两份 PDF 的自检。

## 许可

MIT。仓库地址：<https://github.com/karl-bro/AAAvocabDictation>（仓库名为 `AAAvocabDictation`，
包名与模块名为 `vocab-dictation` / `vocab_dictation`）。若你 fork 到别的账号，
改 `pyproject.toml`、`skill.yaml` 与 `schemas/` 里的 `$id` 即可。
