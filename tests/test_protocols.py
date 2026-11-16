# -*- coding: utf-8 -*-
"""三种接入协议各跑一遍：CLI / MCP stdio / HTTP JSON。"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from vocab_dictation import cli, mcp_server


# ---------------- CLI ----------------

def test_cli_capabilities(capsys):
    assert cli.main(["capabilities"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skill"] == "vocab-dictation"


def test_cli_call(capsys, bank):
    assert cli.main(["call", "--action", "bank.stats", "--bank", bank]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["data"]["词条总数"] == 7


def test_cli_call_failure_exit_code(capsys, tmp_path):
    code = cli.main(["call", "--action", "bank.stats", "--bank",
                     str(tmp_path / "missing.xlsx")])
    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["error"]["code"] == "BANK_NOT_FOUND"


# ---------------- MCP ----------------

def test_mcp_initialize_and_list():
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION
    assert init["result"]["serverInfo"]["name"] == "vocab-dictation"

    listed = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = listed["result"]["tools"]
    assert len(tools) == 1 and tools[0]["name"] == "vocab_dictation"
    assert "action" in tools[0]["inputSchema"]["properties"]


def test_mcp_tools_call(bank):
    reply = mcp_server.handle({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "vocab_dictation",
                   "arguments": {"action": "bank.stats",
                                 "params": {"bank": bank}}},
    })
    payload = json.loads(reply["result"]["content"][0]["text"])
    assert payload["ok"] and reply["result"]["isError"] is False


def test_mcp_notification_is_silent():
    assert mcp_server.handle({"jsonrpc": "2.0",
                              "method": "notifications/initialized"}) is None


def test_mcp_unknown_method():
    reply = mcp_server.handle({"jsonrpc": "2.0", "id": 4, "method": "x/y"})
    assert reply["error"]["code"] == -32601


# ---------------- HTTP ----------------

def test_http_call_roundtrip(bank):
    from vocab_dictation.http_server import Handler
    Handler.bank = bank
    Handler.token = None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            assert json.loads(r.read())["ok"] is True

        req = urllib.request.Request(
            base + "/call",
            data=json.dumps({"action": "bank.stats"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read())
        assert res["ok"] and res["data"]["词条总数"] == 7

        with urllib.request.urlopen(base + "/capabilities", timeout=5) as r:
            assert json.loads(r.read())["skill"] == "vocab-dictation"
    finally:
        srv.shutdown()
        srv.server_close()


def test_http_rejects_bad_token(bank):
    from vocab_dictation.http_server import Handler
    Handler.bank = bank
    Handler.token = "secret"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{srv.server_address[1]}/call",
            data=b'{"action":"bank.stats"}',
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "应当 401"
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        Handler.token = None
        srv.shutdown()
        srv.server_close()
