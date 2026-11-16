# -*- coding: utf-8 -*-
"""示例 4：MCP 客户端视角（Claude Desktop / Cursor 就是这样接的）。

    python examples/04_mcp_client.py

脚本会以子进程方式启动 ``python -m vocab_dictation mcp``，走标准 MCP 握手：
initialize → notifications/initialized → tools/list → tools/call。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _console import utf8_stdout

from vocab_dictation import dispatch

REPO = Path(__file__).resolve().parent.parent
ITEMS = json.loads((REPO / "assets" / "sample_items.json").read_text(encoding="utf-8"))


class McpClient:
    def __init__(self, bank: str):
        env = dict(os.environ)
        # 未 pip install -e . 时，让子进程能找到 src 布局
        env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
        env["VOCAB_DICTATION_BANK"] = bank
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "vocab_dictation", "mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1, env=env)

    def request(self, id_: int, method: str, params: dict | None = None) -> dict:
        msg = {"jsonrpc": "2.0", "id": id_, "method": method}
        if params:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def notify(self, method: str) -> None:
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


def main() -> None:
    utf8_stdout()
    work = Path(tempfile.mkdtemp(prefix="vocab-mcp-"))
    bank = work / "词库.xlsx"
    dispatch("bank.init", {"path": str(bank)})
    dispatch("bank.add_items", {"bank": str(bank), "items": ITEMS,
                                "source": "demo-p1", "date": "2026-11-16"})

    c = McpClient(str(bank))
    try:
        init = c.request(1, "initialize", {"protocolVersion": "2024-11-05",
                                           "capabilities": {},
                                           "clientInfo": {"name": "demo", "version": "0"}})
        print("握手:", init["result"]["serverInfo"])
        c.notify("notifications/initialized")

        tools = c.request(2, "tools/list")["result"]["tools"]
        print("工具数:", len(tools), "| 名称:", tools[0]["name"])

        call = c.request(3, "tools/call", {
            "name": "vocab_dictation",
            "arguments": {"action": "dictation.sample",
                          "params": {"n": 4, "seed": 99}},
        })
        payload = json.loads(call["result"]["content"][0]["text"])
        print("抽样结果:", payload["data"]["count"], "题",
              [i["英文"] for i in payload["data"]["items"]])
        print("isError:", call["result"]["isError"])
    finally:
        c.close()


if __name__ == "__main__":
    main()
