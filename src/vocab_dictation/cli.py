# -*- coding: utf-8 -*-
"""命令行入口：``vocabdict <子命令>``。

设计给人和脚本两用：

    vocabdict capabilities
    vocabdict call --action dictation.sample --params '{"n": 20}' --bank 词库.xlsx
    vocabdict call --action grading.apply --file req.json
    vocabdict serve --port 8800
    vocabdict mcp
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .api import VERSION, capabilities, dispatch


def _load_params(args: argparse.Namespace) -> dict[str, Any]:
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            payload = json.load(f)
        if "action" in payload:
            return payload
        return {"action": args.action, "params": payload}
    raw = args.params or "{}"
    return {"action": args.action, "params": json.loads(raw)}


def _emit(obj: Any, pretty: bool) -> int:
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    text = json.dumps(obj, ensure_ascii=False, indent=2 if pretty else None)
    print(text)
    if isinstance(obj, dict) and obj.get("ok") is False:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="vocabdict",
                                 description="vocab-dictation 统一命令行入口")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capabilities", help="输出能力清单（含参数 JSON Schema）")
    p_cap.add_argument("--pretty", action="store_true")

    p_call = sub.add_parser("call", help="执行单个动作")
    p_call.add_argument("--action", required=True,
                        help="动作名，如 dictation.sample（见 capabilities）")
    p_call.add_argument("--params", help="JSON 字符串参数")
    p_call.add_argument("--file", help="请求体 JSON 文件（{action,params} 或纯参数）")
    p_call.add_argument("--bank", help="词库 xlsx 路径")
    p_call.add_argument("--pretty", action="store_true")

    p_serve = sub.add_parser("serve", help="启动 HTTP JSON 接口")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8800)
    p_serve.add_argument("--bank")
    p_serve.add_argument("--token", help="可选 Bearer Token")

    sub.add_parser("mcp", help="以 MCP stdio 服务运行（Claude/Cursor 等可直接挂载）")

    sub.add_parser("version", help="打印版本号")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "version":
        print(VERSION)
        return 0
    if args.cmd == "capabilities":
        return _emit(capabilities(), args.pretty)
    if args.cmd == "serve":
        from .http_server import serve
        serve(args.host, args.port, bank=args.bank, token=args.token)
        return 0
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main
        return mcp_main()
    if args.cmd == "call":
        payload = _load_params(args)
        res = dispatch(payload.get("action", ""), payload.get("params") or {},
                       bank=args.bank)
        return _emit(res, args.pretty)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
