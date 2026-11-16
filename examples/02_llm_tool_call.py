# -*- coding: utf-8 -*-
"""示例 2：把技能挂到任意大模型应用（OpenAI function calling / Anthropic tool use）。

核心只有三步：
1）用 ``capabilities()`` 生成工具声明；
2）把模型返回的 tool_call 原样交给 ``dispatch()``；
3）把 ``dispatch`` 的 JSON 信封作为 tool 消息喂回模型。

本示例不联网、不依赖 SDK，用一段“假模型”的 tool_call 演示这三步。
真实接入见 docs/integration.md。
"""
import json

from _console import utf8_stdout
from vocab_dictation import capabilities, dispatch

TOOL_NAME = "vocab_dictation"


def openai_tools() -> list[dict]:
    """生成 OpenAI Chat Completions 的 tools 声明。"""
    cap = capabilities()
    actions = [a["action"] for a in cap["actions"]]
    return [{
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "考研生词听写闭环：入库、出卷、批改、报告、摘帽。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": actions},
                    "params": {"type": "object", "additionalProperties": True},
                    "bank": {"type": "string", "description": "词库 xlsx 路径"},
                },
                "required": ["action"],
            },
        },
    }]


def anthropic_tools() -> list[dict]:
    """生成 Anthropic Messages API 的 tools 声明。"""
    spec = openai_tools()[0]["function"]
    return [{"name": spec["name"], "description": spec["description"],
             "input_schema": spec["parameters"]}]


def run_tool_call(tool_call: dict, bank: str | None = None) -> dict:
    """把模型的一次 tool_call 变成一次真实执行，返回可回填的 tool 消息。"""
    args = json.loads(tool_call["function"]["arguments"])\
        if isinstance(tool_call["function"]["arguments"], str)\
        else tool_call["function"]["arguments"]
    res = dispatch(args["action"], args.get("params") or {}, bank=args.get("bank") or bank)
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "name": TOOL_NAME,
        "content": json.dumps(res, ensure_ascii=False),
    }


if __name__ == "__main__":
    utf8_stdout()
    import tempfile
    from pathlib import Path

    ITEMS = json.loads((Path(__file__).resolve().parent.parent / "assets" /
                        "sample_items.json").read_text(encoding="utf-8"))
    work = Path(tempfile.mkdtemp(prefix="vocab-tool-"))
    bank = str(work / "词库.xlsx")
    dispatch("bank.init", {"path": bank})
    dispatch("bank.add_items", {"bank": bank, "items": ITEMS,
                               "source": "demo-p1", "date": "2026-11-16"})

    print("OpenAI tools 声明（截断展示）：")
    print(json.dumps(openai_tools(), ensure_ascii=False)[:400], "…\n")

    # 假设模型已经决定：查一下词库状态
    fake_call = {
        "id": "call_demo_1",
        "type": "function",
        "function": {"name": TOOL_NAME,
                     "arguments": json.dumps({"action": "bank.stats",
                                              "params": {"bank": bank}})},
    }
    msg = run_tool_call(fake_call)
    payload = json.loads(msg["content"])
    print("回填给模型的 tool 消息：")
    print(json.dumps(msg, ensure_ascii=False, indent=2)[:600])
    print("\n模型可直接读到 ok =", payload["ok"], "，词条总数 =",
          payload["data"]["词条总数"])
