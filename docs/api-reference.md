# API 参考

统一入口：

```python
dispatch(action: str, params: dict | None = None, bank: str | None = None) -> dict
```

`schema` 级细节以运行时 `capabilities()`（或 `schemas/capabilities.json`）为准，
本文只讲“怎么用、返回什么形状”。

## 请求

```json
{"action": "dictation.sample", "params": {"n": 20, "seed": 7}, "bank": "E:/vocab/生词词库.xlsx"}
```

- `bank` 可放在 `params.bank`、`dispatch` 的第三个参数、或环境变量 `VOCAB_DICTATION_BANK`（优先级从高到低）。
- 未提供词库且动作需要词库 → `BANK_REQUIRED`。

## 响应信封

```json
{
  "ok": true,
  "action": "dictation.sample",
  "version": "1.0.0",
  "data": {"count": 20, "items": [ ... ]},
  "warnings": [],
  "error": null,
  "meta": {"elapsed_ms": 12, "bank": "E:/vocab/生词词库.xlsx"}
}
```

失败时 `ok=false`、`data=null`、`error={code,message,details}`。

### 错误码

| code | 含义 | 典型处理 |
| --- | --- | --- |
| `INVALID_ACTION` | 动作名不存在 | 从 `error.details.available` 选正确动作 |
| `INVALID_PARAMS` | 缺参/类型错 | 按 `details.missing` 补齐 |
| `BANK_REQUIRED` | 没给词库路径 | 传 `bank` 或设环境变量 |
| `BANK_NOT_FOUND` | 文件不存在 | 先 `bank.init`，或确认路径 |
| `BANK_EXISTS` | 建库目标已存在 | 确认后传 `overwrite: true` |
| `DUPLICATE_BATCH` | 该批次号已批改过 | 确认重批后传 `allow_duplicate: true` |
| `BANK_ERROR` | 词库结构/字段不合法 | 检查列名与字段值枚举 |
| `RENDER_FAILED` | PDF 渲染或自检失败 | 检查 items/meta；确认装 `[pdf]` |
| `FILE_NOT_FOUND` | 输入文件（图片/JSON）不存在 | 修正路径 |
| `INTERNAL_ERROR` | 未预期异常 | 原样上报，附 `message` |

HTTP 层另有 `BAD_JSON` / `UNAUTHORIZED` / `NOT_FOUND` / `PAYLOAD_TOO_LARGE`。

---

## 动作清单

### skill.capabilities

- 参数：无
- 返回：`{skill, version, protocol, description, actions:[{action, summary, returns, input_schema}]}`
- 用途：让模型/客户端自省，不用背文档。

### bank.init

创建空词库（`使用说明` / `总词库` / `错题本` / `听写记录` 四张表）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | string | 是 | — | xlsx 路径，目录不存在会自动创建 |
| `overwrite` | bool | 否 | false | 已存在时是否重建（**会清空旧数据**） |

返回：`{"path": "…/生词词库.xlsx"}`

### bank.add_items

词条入库，自动分配 `W0001` 式 ID；`来源+序号+英文` 相同视为重复并跳过。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source` | string | 是 | 来源页，如 `v.L5-p1` |
| `items` | array | 是 | `[{序号,类型,英文,词性,中文释义,标记,等号链,备注}]` |
| `date` | string | 否 | `YYYY-MM-DD`，默认今天 |

字段枚举：`类型 ∈ {主词, 扩展词, 词组}`，`标记 ∈ {普通, 重点词, 熟词僻义}`，
`等号链 ∈ {是, ""}`。

返回：`{"added": ["W0011"...], "skipped": [...], "total": 30, "ids": [...]}`

### bank.list_items

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `query` | string | 英文/中文包含匹配 |
| `source` | string | 按来源过滤 |
| `status` | enum | `未听写` / `学习中` / `已掌握` |
| `mark` | enum | `普通` / `重点词` / `熟词僻义` |
| `item_type` | enum | `主词` / `扩展词` / `词组` |
| `limit` | int | 上限 |

返回：`{"count": n, "items": [词条…]}`

### bank.update_item

只改可编辑字段，不碰统计列（`听写次数/正确次数/错误次数/连续正确`）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `item_id` | string | 是 | 如 `W0012` |
| `fields` | object | 是 | 可改：`英文/中文释义/词性/标记/等号链/备注/状态/类型` |

返回：`{"词条ID": "...", "changed": ["中文释义", ...], "item": {…最新整行…}}`

### bank.stats

返回：

```json
{"词条总数": 19, "按状态": {"未听写": 19}, "按标记": {...}, "按类型": {...},
 "等号链成员": 3, "错题总数": 0, "待复习错题": 0, "已摘帽错题": 0,
 "听写批次数": 0, "最近批次": [], "最近听写日期": null}
```

### dictation.batch_id

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `date` | string | `YYYY-MM-DD`，默认今天 |

返回：`{"batch_id": "D20261116-01"}`（同一天第二次调用得到 `-02`，前提是第一次已写入听写记录）。

### dictation.sample

错题优先 + 分层随机；**返回顺序即题号**。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `n` | int | 是 | 题量 |
| `scope` | object | 否 | `{来源:[…], 类型:[…], 标记:[…], 序号区间:[lo,hi], 序号集合:[…]}`，可叠加 |
| `seed` | int | 否 | 复现同一天同一顺序 |
| `wrong_ratio` | number | 否 | 错题最多占比，默认 0.6 |

返回：`{"count": n, "items": [词条…]}`

### dictation.shuffle_all

**全量打乱，不补题、不做错题优先**。用于“把当天这批词全部听写一遍”。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `scope` | object | 同 `sample`；省略=整个词库 |
| `seed` | int | 复现顺序 |

返回：`{"count": N, "items": [词条…]}`

### dictation.build_pdf

生成填空版 + 答案版，并自动自检（页数、题号连续、中文与答案文本齐全）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `items` | array | 是 | 顺序即题号 |
| `meta` | object | 是 | 必须含 `批次ID`、`日期`；可选 `范围`、`说明` |
| `outdir` | string | 是 | 输出目录 |
| `prefix` | string | 否 | 文件名前缀，默认 `听写_<日期>` |

返回：`{"verify": "OK", "cloze": "…_填空版.pdf", "answer": "…_答案版.pdf"}`

首字母提示规则见 [scoring-rules.md](scoring-rules.md) 与 `SKILL.md`：
仅等号链成员提示，同链前缀相同则提示到第 n+1 个字母。

### grading.preview

只判分，**不写库**。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `batch_id` | string | 是 | 批次号 |
| `graded` | array | 是 | `[{词条ID, 我的答案, override?}]`，顺序即题号 |
| `date` | string | 否 | 默认今天 |
| `scope` | string | 否 | 范围描述，写进记录/报告 |

返回：

```json
{"批次ID": "...", "日期": "...", "范围": "...", "题数": 19, "得分": 18.5, "满分": 19.0,
 "正确率": 0.9474, "平均得分率": 0.9737, "满分题数": 18, "错题数": 1,
 "重点题数": 1, "重点正确数": 1, "错因统计": {"拼写错误": 1},
 "明细": [{"题号":1,"词条ID":"W0001","中文释义":"…","英文":"…",
          "我的答案":"…","得分":0.5,"错误类型":"拼写错误","批注":"差 1 个字母…"}]}
```

`override` 用于人工裁定：`{"得分": 1, "错误类型": "", "批注": "连笔视为正确"}`。

### grading.apply

同 `preview` 参数，另加：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `note` | string | "" | 写入听写记录备注 |
| `allow_duplicate` | bool | false | 该批次已存在时是否强制重写 |

副作用：更新总词库统计与状态、写错题本、写听写记录、连续两次满分自动摘帽。
返回同 `preview`，并附 `"已写入": true`。

### report.build

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `result` | object | 二选一 | `grading.apply/preview` 的返回 |
| `result_path` | string | 二选一 | 或从 JSON 文件读 |
| `out` | string | 是 | 报告 PDF 路径 |

返回：`{"path": "…pdf", "verify": "OK"}`

### submission.prepare

答卷照片预处理（需 `[image]` extra）：小角度纠偏 → 检测多页拼接并分割 → 灰度/对比增强。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `images` | array | 是 | 照片路径列表 |
| `outdir` | string | 是 | 输出目录 |

返回：`{"页数": 2, "页面": [{文件, 宽, 高, 纠偏角度, 警告, 来源, 分页依据}]}`；
`警告` 非空时（宽 <1400px）应要求用户重拍。
