# 装到各大模型应用：提示词 + 工具声明对照表

> 目标：让任何支持 tool calling 的应用，把本技能装进去就能用，不需要改业务代码。
> 三条原则先记住：**提示词放 system、工具声明用现成 schema、业务逻辑一律交给 `dispatch`。**

## 0. 通用三步

```bash
pip install "vocab-dictation[pdf]"        # 出卷/报告需要 pdf extra
vocabdict capabilities --pretty > capabilities.json   # 看看能做什么
```

1. **系统提示**：把 `prompts/system_prompt.md` 整段放进应用的 system 角色（或「人设/提示词」设置）。
2. **工具声明**：不要手写参数表，直接用
   - OpenAI：`schemas/tool.openai.json`
   - Anthropic：`schemas/tool.anthropic.json`
   - Dify / Coze / 任意 OpenAPI 导入：`schemas/openapi.json`
   - Gemini：同一份 JSON Schema 放进 `functionDeclarations.parameters`
3. **执行**：工具被调用时，把 `{action, params}` 交给 `dispatch()`（或 `POST /call`），
   把返回的信封原样回给模型。

选前面三个平台之一时，系统提示里的 `{词库路径}` 建议换成固定值或环境变量
`VOCAB_DICTATION_BANK`，免得模型每轮都要问。

---

## 1. OpenAI（Chat Completions / Responses API）

```python
import json
from openai import OpenAI
from vocab_dictation import dispatch

client = OpenAI()
system = open("prompts/system_prompt.md", encoding="utf-8").read()
tool = json.load(open("schemas/tool.openai.json", encoding="utf-8"))

def run(action: str, params: dict | None = None) -> str:
    res = dispatch(action, params or {})
    return json.dumps(res, ensure_ascii=False)

messages = [{"role": "system", "content": system},
            {"role": "user", "content": "把今天这两页全部打乱出卷"}]

while True:
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=[tool],
        tool_choice="auto",
    )
    msg = r.choices[0].message
    if not msg.tool_calls:
        print(msg.content)
        break
    messages.append(msg)
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)
        out = run(args["action"], args.get("params"))
        messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
```

- **Responses API**：把工具改成扁平结构 `{"type": "function", "name": "vocab_dictation",
  "description": ..., "parameters": ...}`，其余流程相同。
- 坑：`strict: true` 要求所有字段必填且不允许可选参数，本项目的 `params` 是按动作变化的，
  **不要开 strict**，否则 `action` 之外的参数会被判非法。

---

## 2. Anthropic Claude（Messages API）

```python
import json
from anthropic import Anthropic
from vocab_dictation import dispatch

client = Anthropic()
system = open("prompts/system_prompt.md", encoding="utf-8").read()
tools = [json.load(open("schemas/tool.anthropic.json", encoding="utf-8"))]

messages = [{"role": "user", "content": "全部词汇打乱出卷"}]
while True:
    r = client.messages.create(model="claude-sonnet-4-5", system=system,
                               tools=tools, messages=messages, max_tokens=4096)
    if r.stop_reason != "tool_use":
        print("".join(b.text for b in r.content if b.type == "text"))
        break
    messages.append({"role": "assistant", "content": r.content})
    results = []
    for block in r.content:
        if block.type == "tool_use":
            env = dispatch(block.input["action"], block.input.get("params") or {})
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(env, ensure_ascii=False)})
    messages.append({"role": "user", "content": results})
```

- 坑：`tool_result.content` 必须是**字符串**，不能直接塞 dict；
  业务失败也要作为 `tool_result` 返回（`is_error: true` 可选），别把 400 变成异常抛给模型。

---

## 3. Google Gemini（functionDeclarations）

Gemini 的 `parameters` 用的是 OpenAPI 子集，直接复用 `schemas/tool.openai.json` 里的
`function.parameters` 即可（类型都是小写 `object`/`string`/`array`）。

```python
import json
from google import genai
from google.genai import types
from vocab_dictation import dispatch

tool = json.load(open("schemas/tool.openai.json", encoding="utf-8"))["function"]
decl = types.FunctionDeclaration(
    name=tool["name"], description=tool["description"],
    parameters=tool["parameters"],
)

client = genai.Client()
system = open("prompts/system_prompt.md", encoding="utf-8").read()
chat = client.chats.create(model="gemini-2.5-flash",
                           config=types.GenerateContentConfig(
                               system_instruction=system,
                               tools=[types.Tool(function_declarations=[decl])]))
```

- 若 SDK 版本较新，可用 `parameters_json_schema=` 传完整 JSON Schema；
  老版本只认 OpenAPI 子集，`$schema`、`$id` 之类字段要先删掉（本项目生成的声明里没有这些键）。
  若 `parameters=` 不接受 dict，改成 `parameters=types.Schema(**tool["parameters"])` 逐层构造。
- 坑：Gemini 会把函数调用结果包成 `function_response`，记得用 `types.Part.from_function_response`
  回填，而不是塞一段纯文本。

---

## 4. LangChain / LangGraph

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from vocab_dictation import dispatch

class VocabArgs(BaseModel):
    action: str = Field(description="动作名，先用 skill.capabilities 查询")
    params: dict = Field(default_factory=dict, description="动作参数")

def _run(action: str, params: dict | None = None, **_: object) -> str:
    import json
    return json.dumps(dispatch(action, params or {}), ensure_ascii=False)

tool = StructuredTool.from_function(
    func=_run, name="vocab_dictation",
    description="生词听写闭环：入库/出卷/批改/报告/词库维护",
    args_schema=VocabArgs,
)
llm_with_tools = llm.bind_tools([tool])
```

- LangGraph 里把 `tool` 放进 `ToolNode`，`dispatch` 是同步函数，包一层 `ainvoke` 即可。
- 坑：部分模型要求工具返回 `str`，别直接返回 dict（会被序列化成 Python repr）。

---

## 5. LlamaIndex

```python
from llama_index.core.tools import FunctionTool
from vocab_dictation import dispatch

tool = FunctionTool.from_defaults(
    fn=lambda action, params=None: dispatch(action, params or {}),
    name="vocab_dictation",
    description="生词听写闭环：入库/出卷/批改/报告/词库维护",
)
agent = ReActAgent.from_tools([tool], llm=llm, verbose=True)
```

- 坑：LlamaIndex 默认把工具返回值转成字符串塞进 prompt；信封较大时建议在 `fn` 里只回
  `data` 的关键字段，避免上下文被 PDF 路径和明细挤爆。

---

## 6. Dify（自定义工具 / OpenAPI 导入）

1. 起服务：`vocabdict serve --port 8800 --bank "{词库路径}" --token "{你的token}"`
2. 工具 → 自定义 → 创建 → **导入 OpenAPI**：把 `schemas/openapi.json` 里的
   `servers.url` 改成你的地址（本机调试用 `http://127.0.0.1:8800`，容器里用
   `http://host.docker.internal:8800`）。
3. 鉴权选 **API Key / Bearer**，填 `{你的token}`。
4. 在 Agent 应用的「提示词」里粘 `prompts/system_prompt.md`，工具勾选 `vocabDictationCall`。

- 坑：Dify 跑在容器里时 `127.0.0.1` 指向容器自身，必须写宿主机地址；否则一直「连接失败」。
- 坑：`/call` 业务失败返回 400，Dify 会把 400 当工具执行失败；
  若你的编排对失败敏感，可在工具后处理里把 400 的 body 当正常结果读出来（信封里 `ok=false` 自带原因）。

---

## 7. Coze（插件 / OpenAPI 导入）

1. 插件 → 创建插件 → 导入 OpenAPI，用同一份 `schemas/openapi.json`，
   `servers.url` 换成**公网可达**地址（本机可用 `cloudflared tunnel --url http://127.0.0.1:8800`
   或 ngrok 临时开一个）。
2. 鉴权选 Service / API Key，Header 名 `Authorization`，值 `Bearer {token}`。
3. Bot 的「人设与回复逻辑」里粘 `prompts/system_prompt.md`，插件挂上刚建的工具。

- 坑：Coze 超时较短（通常 5–10s），出卷/批改这种带 PDF 渲染的调用容易超时；
  把 `dictation.build_pdf`、`grading.apply`、`report.build` 拆成独立插件动作，
  并让 Bot 一次只调一个，超时概率会明显下降。

---

## 8. MCP 客户端（Claude Desktop / Cursor / 任意 MCP Host）

本项目的 MCP 服务是 stdio、单工具 `vocab_dictation`、协议 `2024-11-05`。

Claude Desktop（`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "vocab-dictation": {
      "command": "vocabdict",
      "args": ["mcp"],
      "env": { "VOCAB_DICTATION_BANK": "E:/vocab/词库.xlsx" }
    }
  }
}
```

Cursor（`~/.cursor/mcp.json`）结构相同。Windows 上若 `vocabdict` 不在 PATH，
把 `command` 写成虚拟环境里的完整路径，例如
`"C:/Users/me/.venv/Scripts/vocabdict.exe"`。

- 坑：MCP Host 通常没有「系统提示」入口，工具描述就是它看到的全部；
  所以把 `prompts/system_prompt.md` 缩减成一段项目说明（或 `CLAUDE.md`、`.cursor/rules`）
  放进项目目录，效果等价。
- 坑：stdio 服务不要往 stdout 打调试信息，会污染 JSON-RPC 流；本项目日志走 stderr。

---

## 9. 自建后端（任意语言）

```bash
curl -s http://127.0.0.1:8800/call \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"dictation.shuffle_all","params":{"scope":{"来源":["v.L24-p1"]},"seed":2026}}'
```

把这段请求包成你框架里的一个工具（参数 `action` + `params`），
系统提示用 `prompts/system_prompt.md`，就完成了接入。语言无关，也不需要 Python。

---

## 10. 各平台「系统提示」放哪里

| 平台 | 位置 |
| --- | --- |
| OpenAI Chat Completions | `messages` 里 `role="system"` 的第一条 |
| OpenAI Responses API | `instructions` 字段 |
| Anthropic | `system=` 参数 |
| Gemini | `system_instruction` / `systemInstruction` |
| LangChain | `ChatPromptTemplate` 的 system 消息 |
| LlamaIndex | `ChatPromptTemplate` 或 `agent.system_prompt` |
| Dify | 应用「编排 → 提示词」 |
| Coze | Bot「人设与回复逻辑」 |
| MCP Host | 项目内 `CLAUDE.md` / `.cursor/rules` / 自定义指令 |

## 11. 装完怎么验

1. 问一句「你能做什么」→ 模型应调 `skill.capabilities`，而不是自由发挥。
2. 给它一个不存在的词库路径 → 应得到 `BANK_NOT_FOUND` 并反问，**而不是**自己建库。
3. 让它「全部打乱出卷」→ 应走 `dictation.shuffle_all`，题量等于范围内词条数。
4. 让它批改一份空白卷 → 应全部 0 分、`未作答`，且 `apply` 前先停一次等你确认。
