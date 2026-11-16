---
name: vocab-dictation
description: 考研英语生词本听写闭环。把生词本识别结果入库、按错题优先或全量打乱出卷（填空版+答案版 PDF）、批改手写答案并三档评分、维护错题本与连续两次满分摘帽、输出批改报告。当用户说“背单词 / 生词听写 / 报听写 / 听写单词 / 批改听写 / 生词本 / 出份听写卷”时使用。
version: 1.0.0
license: MIT
---

# vocab-dictation：生词听写闭环技能

本文件是给 **Agent / 大模型** 看的操作契约。人类安装与集成说明见 `README.md`；
参数级细节见 `docs/api-reference.md` 与运行时 `capabilities()`。

## 何时使用

- 用户上传生词本照片，要求识别、入库、听写；
- 用户要求出听写卷（指定数量 / 全量打乱 / 只要主词或词组 / 某几页）；
- 用户上传手写完成稿，要求批改、评分、错题整理；
- 用户问“上次错了哪些词”“这周听写正确率”“词库里还有多少没听写”。

不适用：单纯查单词释义、背单词计划制定、与词库无关的英语问答。

## 安装

```bash
pip install "vocab-dictation[pdf]"     # 出卷/报告需要 pdf extra
```

## 调用方式（四选一，行为完全一致）

| 方式 | 入口 |
| --- | --- |
| Python | `from vocab_dictation import dispatch; dispatch("bank.stats", {"bank": p})` |
| 命令行 | `vocabdict call --action bank.stats --bank 词库.xlsx` |
| HTTP | `vocabdict serve --port 8800` → `POST /call` |
| MCP | `vocabdict mcp`（stdio，工具名 `vocab_dictation`） |

**每次调用都返回同一个信封**：`{ok, action, version, data, warnings, error, meta}`。
不要只看 `data`：`ok=false` 时读 `error.code` 决定下一步（见下表）。

| 错误码 | Agent 应采取的动作 |
| --- | --- |
| `BANK_REQUIRED` | 向用户要词库路径，或用 `bank.init` 新建 |
| `BANK_NOT_FOUND` | 确认路径；不存在则先 `bank.init`（勿静默新建覆盖） |
| `BANK_EXISTS` | 问用户是否重建；只有明确同意才传 `overwrite: true` |
| `INVALID_PARAMS` | 按 `details.missing` 补参数重试，不要改动作名 |
| `DUPLICATE_BATCH` | 该批次已批改过；确认是重批才传 `allow_duplicate: true` |
| `RENDER_FAILED` | 检查 items/meta 完整性；缺 `pdf` extra 时先装依赖 |
| `INTERNAL_ERROR` | 原样把 message 回报用户，不要编造成功 |

## 标准工作流

### 第 1 步 识别并核对（必须先核对再入库）

1. 读用户上传的生词本照片，按 `prompts/extract_items.md` 的规则与 JSON 契约解析。
2. **回传 Markdown 表格让用户核对**（序号/类型/英文/词性/中文/标记/等号链/备注），
   不确定项写进备注。用户确认或修正后才继续。
3. `bank.add_items`：`source` 用「页眉编号-p页码」（如 `v.L5-p1`），`date` 用当天。
   同来源重复上传按 `来源+序号+英文` 自动去重，重复条数会进 `warnings`。

### 第 2 步 出卷

1. 取批次号：`dictation.batch_id`（得到 `D20261116-01` 形式）。
2. 选题，二选一：
   - 用户给了数量 N、或要“错题优先/抽查” → `dictation.sample`，`params: {n: N, scope?}`；
   - 用户要“**全部词汇打乱**”“不用补题” → `dictation.shuffle_all`（不传 `n`，返回全量）。
   - **默认范围 = 用户当天上传的那几页**：把当天来源放进 `scope: {来源: [...]}`，
     只有用户明确说“从整个词库抽”才不加 `scope`。
3. `dictation.build_pdf`：`meta` 必须含 `批次ID`、`日期`，可带 `范围`、`说明`。
   返回 `{cloze, answer, verify}`。
4. **只把填空版交付给用户**（答案版留档，用户交卷前不展示）；
   `verify` 非 `OK` 时按自检报告修数据后重跑，不要直接交。

### 第 3 步 批改

1. 用户上传完成稿后，先 `submission.prepare` 纠偏/分页/增强（需 `[image]` extra），
   有“分辨率偏低”警告就让用户重拍。
2. 按 `prompts/read_submission.md` **逐字转写**手写答案（不要顺手纠正拼写）。
3. 对齐题号：第 i 题 → `{"词条ID": items[i-1]["词条ID"], "我的答案": "..."}`。
4. 先 `grading.preview` 展示逐题得分与错因，用户确认后 `grading.apply` 正式写库。
5. `report.build` 生成报告，回报：得分/正确率、错因分布、需立即抄默的词、复习建议。

## 评分口径（固定，不得自行放宽）

| 情形 | 得分 | 错误类型 |
| --- | --- | --- |
| 拼写完全正确（斜杠同义词任一正确） | 1 | — |
| 单词错 1~2 个字母且整体可辨认（3~4 字母短词只容错 1 个） | 0.5 | 拼写错误 |
| 拼写偏差大、无法辨认 | 0 | 完全不会 |
| 未作答 | 0 | 未作答 |
| 词组漏词 | 0 | 词组漏词 |
| 词组多词 / 拼写错 | 0 | 词组错误 |
| 词组单词全对但顺序错 | 0 | 词序错误 |

- **半对也算一次错误**：`连续正确` 清零并进错题本。
- 摘帽：错题**连续 2 次**得 1 分即摘帽；期间任一次未满分，计数重新开始。

## 首字母提示规则

- 仅 `等号链=是` 的成员显示字母提示，**且包括 `=` 前的主词**。
- 同链成员前 n 个字母相同 → 提示到第 **n+1** 个字母（前缀），否则只给首字母。
- 非链项（普通主词、扩展词、词组、非链重点/熟僻词）**一律不提示**，用户追问也不透露。

## 已知坑

1. `grading.apply` 同一批次重复执行会重复计分 → 已内置 `DUPLICATE_BATCH` 保护，重批要显式 `allow_duplicate`。
2. 斜杠项（`optional/selective course`）是**一个**听写项，答案是其中一支；
   直接把整串 `a/b` 当答案提交会被判词组错误。
3. 词组答多一个冠词（`a pink slip` vs `pink slip`）判 0，不要当成“接近正确”。
4. 词库是单文件 xlsx，多人/多进程并发写会互相覆盖；批量操作请串行。
5. 中文环境中旧版脚本曾出现 stdout 被吞，Python 调用请加 `-u` 或直接用 SDK（无此问题）。
