# -*- coding: utf-8 -*-
"""MCP（Model Context Protocol）stdio 服务端。

挂在 Claude Desktop / Cursor / 任何支持 MCP 的客户端后，模型可以直接看到
一个 ``vocab_dictation`` 工具，并通过 ``action`` 参数调用全部能力。

协议：行分隔 JSON-RPC 2.0（stdin/stdout），兼容 MCP 2024-11-05。
"""
from __future__ import annotations

import json
import sys
from typing import Any

from .api import ACTION_SPECS, VERSION, dispatch

PROTOCOL_VERSION = "2024-11-05"
TOOL_NAME = "vocab_dictation"

_DESCRIPTION = (
    "考研生词本听写闭环工具。按 action 调用："
    "bank.init / bank.add_items / bank.list_items / bank.update_item / bank.stats / "
    "dictation.batch_id / dictation.sample / dictation.shuffle_all / "
    "dictation.build_pdf / grading.preview / grading.apply / report.build / "
    "submission.prepare / skill.capabilities。"
    "输入为结构化 JSON（词条、答案、批次号），输出为 {ok,data,error} 信封。"
)


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": _DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": sorted(ACTION_SPECS),
                           "description": "要执行的动作"},
                "params": {"type": "object", "additionalProperties": True,
                           "description": "该动作的参数，见 action 对应的 input_schema"},
                "bank": {"type": "string",
                         "description": "词库 xlsx 绝对路径；也可用服务进程的环境变量"},
            },
            "required": ["action"],
        },
    }


def _respond(id_: Any, result: Any = None, error: dict | None = None) -> dict:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    """处理单条 JSON-RPC 消息；通知类消息返回 None。"""
    method = msg.get("method")
    id_ = msg.get("id")

    if method == "initialize":
        return _respond(id_, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "vocab-dictation", "version": VERSION},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _respond(id_, {})
    if method == "tools/list":
        return _respond(id_, {"tools": [_tool_schema()]})
    if method == "tools/call":
        args = (msg.get("params") or {}).get("arguments") or {}
        res = dispatch(args.get("action", ""), args.get("params") or {},
                       bank=args.get("bank"))
        text = json.dumps(res, ensure_ascii=False)
        return _respond(id_, {
            "content": [{"type": "text", "text": text}],
            "isError": not res["ok"],
        })
    if method in ("shutdown", "exit"):
        return _respond(id_, {})
    return _respond(id_, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    # MCP stdio 通道按规范就是 UTF-8；显式重设，避免宿主 locale（如 Windows cp1252）
    # 让含中文的响应编码失败、把 JSON-RPC 流写坏。
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps(_respond(None, error={
                "code": -32700, "message": f"parse error: {e}"})) + "\n")
            sys.stdout.flush()
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
