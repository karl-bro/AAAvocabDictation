# -*- coding: utf-8 -*-
"""示例 3：用 HTTP 把技能接进任何语言的应用。

    python examples/03_http_client.py

脚本内部会在 127.0.0.1 的随机端口起一个服务，演示 POST /call 与 GET /capabilities。
生产环境请单独启动：``vocabdict serve --port 8800 --bank 词库.xlsx``

任何语言只需要：

    POST http://host:8800/call
    Content-Type: application/json
    {"action": "dictation.sample", "params": {"n": 20}}
"""
import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from vocab_dictation import dispatch
from vocab_dictation.http_server import Handler

ITEMS = json.loads((Path(__file__).resolve().parent.parent / "assets" /
                    "sample_items.json").read_text(encoding="utf-8"))


def post(base: str, payload: dict) -> dict:
    req = urllib.request.Request(
        base + "/call",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 业务失败返回 400 + 标准错误信封，仍按 JSON 解析
        return json.loads(e.read().decode("utf-8"))


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="vocab-http-"))
    bank = work / "词库.xlsx"

    # 先把词库准备好（同进程直接调用，省一次 HTTP）
    dispatch("bank.init", {"path": str(bank)})
    dispatch("bank.add_items", {"bank": str(bank), "items": ITEMS,
                                "source": "demo-p1", "date": "2026-11-16"})

    Handler.bank = str(bank)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        print("health:", get(base, "/health"))
        cap = get(base, "/capabilities")
        print("可用动作数:", len(cap["actions"]))
        res = post(base, {"action": "dictation.shuffle_all", "params": {"seed": 7}})
        print("全量打乱题数:", res["data"]["count"],
              "| 前三题:", [i["英文"] for i in res["data"]["items"][:3]])
        bad = post(base, {"action": "nope"})
        print("错误码:", bad["error"]["code"])
    finally:
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    main()
