# prompts/ — 四份可直接粘贴的提示词 + 一份安装手册

本目录只放**对模型的契约**，不参与业务逻辑。所有判分、统计、排版都在代码里，
提示词只负责「读图、按流程推进、把结果讲清楚」。

| 文件 | 给谁 | 什么时候用 |
| --- | --- | --- |
| `system_prompt.md` | 应用的 **system 角色** | 装技能时第一条就粘它；含动作清单、流程停点、错误码应对、硬规则 |
| `task_prompts.md` | 应用的 **用户消息** | 五类常见任务的发起话术，附「期望动作序列」可用于回归测试 |
| `extract_items.md` | 读图那一步 | 生词本照片 → `bank.add_items` 的 `items` 数组 |
| `read_submission.md` | 读答卷那一步 | 手写答卷 → `grading.preview/apply` 的 `graded` 数组 |
| `../docs/install-prompts.md` | 开发者 | 9 个平台（OpenAI / Claude / Gemini / LangChain / LlamaIndex / Dify / Coze / MCP / 自建）的接法 |

## 安装顺序

1. 粘 `system_prompt.md` 到 system；
2. 挂工具声明：OpenAI 用 `schemas/tool.openai.json`，Anthropic 用 `schemas/tool.anthropic.json`，
   Dify/Coze 用 `schemas/openapi.json`；
3. 用户发任务时用 `task_prompts.md` 里的模板（或让用户自由描述，模型按系统提示走）。

## 设计取舍

- **只用一个工具**：`vocab_dictation({action, params})`。模型上下文里永远只有一份声明，
  加动作不用改提示词，也不用担心 14 个工具互相抢戏。
- **写清停点**：识别后停一次（核对清单）、批改后停一次（预览确认）。
  这不是啰嗦，而是避免模型把「猜测的识别结果」直接写进词库。
- **错误码写成动作**：`DUPLICATE_BATCH → 先问用户`、`BANK_EXISTS → 绝不自动覆盖`，
  给模型的是行为指令，不是错误名词解释。
- **提示词不重复 schema**：参数细节归 `skill.capabilities`，
  提示词只保留「何时用哪个动作」。文档与代码分叉由 `tests/test_schemas.py` 守着。
