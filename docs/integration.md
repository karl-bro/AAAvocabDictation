# 第三方应用集成指南

三种接入形态，按“你的应用能不能改代码、能不能起进程”选择：

| 你的形态 | 推荐接入 | 一次调用成本 |
| --- | --- | --- |
| Python 后端 / 脚本 | `pip install` + SDK | 函数调用 |
| 任意语言后端 / 微服务 | `vocabdict serve` + HTTP | 一次 HTTP |
| 桌面客户端里挂给 Claude/Cursor | `vocabdict mcp` | 一次工具调用 |
| 自研 Agent 框架 | 任一形态 + `capabilities()` 自省 | — |

> 接完工具只是半成品：模型还需要一套行为约束。系统提示、任务模板与各平台
> 提示词放置位置见 [install-prompts.md](install-prompts.md)，Dify/Coze 可直接导入
> `schemas/openapi.json`。

---

## 1. OpenAI function calling

用 `schemas/tool.openai.json`（由 `scripts/export_tool_schemas.py` 从代码生成）：
直接把它放进 `tools`，模型就会按 action 枚举发起调用。

```python
import json
from openai import OpenAI
from vocab_dictation import dispatch

tools = [json.load(open("schemas/tool.openai.json", encoding="utf-8"))]
client = OpenAI()

resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "你是考研生词听写助手。用户要出卷时调用 vocab_dictation。"},
        {"role": "user", "content": "把词库里所有词打乱，出一份听写卷"},
    ],
    tools=tools,
)

for call in resp.choices[0].message.tool_calls or []:
    args = json.loads(call.function.arguments)
    result = dispatch(args["action"], args.get("params") or {},
                      bank="E:/vocab/生词词库.xlsx")
    # 把 result 作为 role=tool 消息回填，让模型继续
    print(json.dumps(result, ensure_ascii=False))
```

关键点：**工具只有一个**，动作靠 `action` 区分。好处是无论词库有多少能力，
模型上下文里永远只有一份工具声明；新增动作不需要改提示词。

## 2. Anthropic tool use

`schemas/tool.anthropic.json` 已经是 Anthropic 的 `{name, description, input_schema}` 形状：

```python
tools = [json.load(open("schemas/tool.anthropic.json", encoding="utf-8"))]
# client.messages.create(..., tools=tools)
```

## 3. 任意语言：HTTP

```bash
vocabdict serve --host 0.0.0.0 --port 8800 --bank /data/生词词库.xlsx --token $TOKEN
```

```javascript
// Node
const r = await fetch("http://host:8800/call", {
  method: "POST",
  headers: {"Content-Type": "application/json", "Authorization": `Bearer ${token}`},
  body: JSON.stringify({action: "dictation.sample", params: {n: 20}}),
});
const {ok, data, error} = await r.json();
```

```bash
# curl
curl -s localhost:8800/call -H 'Content-Type: application/json' \
  -d '{"action":"bank.stats"}'
```

约定：
- 业务成功 `200`，业务失败 `400`，两种都返回同一个 JSON 信封；不要只看状态码。
- `GET /capabilities` 可缓存，用于前端动态生成表单/菜单。
- 未设 token 时接口对本机开放；对公网暴露必须设 `--token` 或 `VOCAB_DICTATION_TOKEN`。

## 4. MCP（Claude Desktop / Cursor / 任何 MCP 宿主）

```json
{
  "mcpServers": {
    "vocab-dictation": {
      "command": "python",
      "args": ["-m", "vocab_dictation", "mcp"],
      "env": {
        "VOCAB_DICTATION_BANK": "E:/vocab/生词词库.xlsx"
      }
    }
  }
}
```

挂载后模型看到工具 `vocab_dictation`，参数 `{action, params?, bank?}`。
stdio + 行分隔 JSON-RPC，兼容 MCP `2024-11-05`；`tools/list` 只暴露一个工具，
`tools/call` 的返回是 `content:[{type:"text", text:"<信封 JSON>"}]`，`isError` 与 `ok` 同步。

## 5. 自研 Agent 框架

推荐启动时拉一次能力清单，再把它转成你框架的内部工具描述：

```python
from vocab_dictation import capabilities
cap = capabilities()
for a in cap["actions"]:
    register_tool(name=a["action"], schema=a["input_schema"], summary=a["summary"])
```

`input_schema` 是标准 JSON Schema（含 `required`、`enum`、`default`），
可以直接喂给 function-calling、结构化输出校验或表单生成器。

---

## 输入输出契约（对接时必须遵守）

1. **纯 JSON**：没有二进制、没有文件句柄、没有对象引用；PDF 只以路径返回。
2. **顺序即题号**：`sample` / `shuffle_all` 返回的 `items` 数组，第 i 个就是第 i 题；
   批改时 `graded[i-1]` 必须对应同一个 `词条ID`。
3. **判分在服务端**：调用方只负责“把用户写的字母原样转写”，不要把纠正后的答案传进来，
   否则会把真实拼写错误判成正确（见 `prompts/read_submission.md`）。
4. **失败要读 `error.code`**，不要 catch 后当成功；`DUPLICATE_BATCH` 是保护，不是 bug。
5. **词库是单文件**：一个词库一个用户/一个设备。多用户场景请给每个用户独立 xlsx，
   或在上层做串行化；本技能不做并发写锁。

## 最小接入清单（第三方应用上线前自查）

- [ ] 词库路径固定（参数 / 环境变量 / 服务启动参数之一）
- [ ] 首次运行有 `bank.init`，且不会在用户不知情时 `overwrite`
- [ ] 出卷只把填空版给用户，答案版留到批改后
- [ ] 批改走 `preview → 用户确认 → apply` 两步
- [ ] `warnings` 会展示给用户（去重条数、自检异常、图片分辨率）
- [ ] 报告生成后校验 `verify == "OK"`
- [ ] HTTP 部署设了 token，且只暴露 `/call`、`/capabilities`、`/health`
