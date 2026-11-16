# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-11-16

首个开源版本：把内部使用的 `vocab-dictation` 技能重构为可复用工程。

### Added

- **统一调用入口** `dispatch(action, params, bank)`：输入输出均为纯 JSON，
  统一信封 `{ok, action, version, data, warnings, error, meta}`，失败也返回结构化错误码。
- **能力自省** `capabilities()`：由 `ACTION_SPECS` 自动派生每个动作的 JSON Schema，
  模型无需背文档即可发现参数。
- **四套适配器**：Python SDK（`VocabDictation` 门面）、CLI（`vocabdict`）、
  零依赖 HTTP 服务（`POST /call`、`GET /capabilities`、`GET /health`，可选 Bearer Token）、
  MCP stdio 服务（单工具 `vocab_dictation`，协议 `2024-11-05`）。
- **全量打乱出卷** `dictation.shuffle_all`：范围内部打乱、不补题、不做错题优先，
  与 `dictation.sample`（错题优先抽样）并列。
- **词库维护动作** `bank.list_items` / `bank.update_item` / `bank.stats`，
  此前只能靠 openpyxl 手改。
- **重复批次保护**：同一 `batch_id` 已写入听写记录时抛 `DUPLICATE_BATCH`，
  需显式 `allow_duplicate: true` 才允许重批，避免听写次数与连续正确被重复累加。
- **PDF 自检**：出卷与报告生成后校验页数、题号连续、中文释义与答案文本齐全，
  结果以 `verify` 返回。
- **工具声明生成器** `scripts/export_tool_schemas.py`：从代码导出
  OpenAI / Anthropic 工具声明与能力清单，避免 schema 与实现分叉。
- **提示词包**：`prompts/system_prompt.md`（通用系统提示：动作清单、流程停点、
  错误码→行为对照、硬规则，附英文精简版）、`prompts/task_prompts.md`（五类任务模板，
  每个标注期望动作序列）、`prompts/README.md`（安装顺序与设计取舍）。
- **平台安装手册** `docs/install-prompts.md`：OpenAI / Anthropic / Gemini /
  LangChain / LlamaIndex / Dify / Coze / MCP 宿主 / 自建后端九种接法，含各自易踩的坑。
- **OpenAPI 描述** `schemas/openapi.json`：供 Dify、Coze 等直接导入，
  action 枚举与 `ACTION_SPECS` 由测试守住一致性。
- **提示词模板**：`prompts/extract_items.md`（生词本照片 → 词条 JSON）、
  `prompts/read_submission.md`（手写答卷 → 逐字答案 JSON）。
- **77 个测试**：评分边界、去重、范围筛选、摘帽生命周期、错误码、CLI、MCP、HTTP、PDF。

### Changed

- 评分内核抽成 `core.py`，与 I/O 完全解耦；三档规则与词组分支持续沿用原口径
  （1 / 0.5 / 0，短词只容错 1 字母），确保历史分数不漂移。
- 交付口径明确区分 `正确率`（满分率）与 `平均得分率`（按 0.5 折算），避免报表歧义。

### Fixed

- 词库不存在时 `bank.stats` 等直连调用返回 `INTERNAL_ERROR`，现统一映射为 `BANK_NOT_FOUND`。
- 中文字体按平台回退（Windows / macOS / Linux Noto、文泉驿），
  全都没有时才退回 CID 字体，并在自检中如实反映文本可抽取性。
- CI 冒烟步骤改为显式 `utf-8-sig` 读回能力清单：Windows runner 的默认 locale
  无法解码含中文的 UTF-8 JSON，此前三个 Windows 矩阵任务均卡在这一步。
- CI 动作升级到 `checkout@v5` / `setup-python@v6`，消除 Node 20 弃用告警。
- Python 支持下限由 3.9 调整为 3.10（3.9 已 EOL，且 `ubuntu-latest` 已无法安装其工具链），
  矩阵同步改为 3.10 / 3.11 / 3.13。
- 示例与 MCP stdio 服务显式使用 UTF-8 输出：Windows / C locale 下打印中文不再
  `UnicodeEncodeError`，MCP 子进程也不会因编码失败把 JSON-RPC 流写坏。

### Known limitations

- 不做 OCR：照片识别由调用方模型完成，本项目只提供契约与提示词。
- 词库为单文件 xlsx，未实现并发写锁；多用户场景需按用户分库或上层串行化。
