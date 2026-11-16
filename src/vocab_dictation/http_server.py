# -*- coding: utf-8 -*-
"""零依赖 HTTP 适配器：把统一接口暴露成 REST 风格 JSON 端点。

适合任意语言/框架的第三方应用接入：

    POST /call   {"action": "bank.stats", "params": {"bank": "词库.xlsx"}}
    GET  /capabilities
    GET  /health

启动：``vocabdict serve --port 8800``
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .api import VERSION, capabilities, dispatch

MAX_BODY = 16 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = f"vocab-dictation/{VERSION}"
    bank: str | None = None
    token: str | None = None

    # -- 工具 --
    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not self.token:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {self.token}"

    def log_message(self, fmt: str, *args: Any) -> None:  # 静音默认日志
        pass

    # -- 路由 --
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "vocab-dictation",
                             "version": VERSION})
        elif self.path == "/capabilities":
            self._json(200, capabilities())
        else:
            self._json(404, {"ok": False, "error": {"code": "NOT_FOUND",
                                                   "message": self.path}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/call":
            self._json(404, {"ok": False, "error": {"code": "NOT_FOUND",
                                                   "message": self.path}})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "error": {"code": "UNAUTHORIZED",
                                                   "message": "缺少或错误的 Bearer Token"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json(413, {"ok": False, "error": {"code": "PAYLOAD_TOO_LARGE",
                                                   "message": f">{MAX_BODY} bytes"}})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError as e:
            self._json(400, {"ok": False, "error": {"code": "BAD_JSON",
                                                   "message": str(e)}})
            return

        res = dispatch(payload.get("action", ""), payload.get("params") or {},
                       bank=self.bank)
        self._json(200 if res["ok"] else 400, res)


def serve(host: str = "127.0.0.1", port: int = 8800,
          bank: str | None = None, token: str | None = None) -> None:
    Handler.bank = os.path.abspath(bank) if bank else os.environ.get("VOCAB_DICTATION_BANK")
    Handler.token = token or os.environ.get("VOCAB_DICTATION_TOKEN")
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"vocab-dictation {VERSION} listening on http://{host}:{port}")
    print(f"  POST /call   GET /capabilities   GET /health")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutdown")
    finally:
        srv.server_close()
