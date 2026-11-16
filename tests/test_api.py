# -*- coding: utf-8 -*-
"""统一接口测试：信封格式、错误码、能力自省、对象门面。"""
import json

import pytest

from vocab_dictation import ToolError, VocabDictation, capabilities, call_json, dispatch


def test_capabilities_exposes_every_action():
    cap = capabilities()
    assert cap["skill"] == "vocab-dictation"
    names = {a["action"] for a in cap["actions"]}
    assert {"bank.init", "dictation.sample", "grading.apply", "report.build"} <= names
    sample = next(a for a in cap["actions"] if a["action"] == "dictation.sample")
    assert sample["input_schema"]["required"] == ["n"]


def test_dispatch_success_envelope(bank):
    res = dispatch("bank.stats", {"bank": bank})
    assert res["ok"] is True and res["action"] == "bank.stats"
    assert res["data"]["词条总数"] == 7
    assert res["error"] is None
    assert res["meta"]["elapsed_ms"] >= 0
    json.dumps(res, ensure_ascii=False)      # 必须可序列化


def test_dispatch_unknown_action(bank):
    res = dispatch("nope.nope", {"bank": bank})
    assert res["ok"] is False
    assert res["error"]["code"] == "INVALID_ACTION"
    assert "available" in res["error"]["details"]


def test_dispatch_requires_bank(monkeypatch):
    monkeypatch.delenv("VOCAB_DICTATION_BANK", raising=False)
    res = dispatch("bank.stats", {})
    assert res["error"]["code"] == "BANK_REQUIRED"


def test_dispatch_bank_not_found(tmp_path):
    res = dispatch("bank.stats", {"bank": str(tmp_path / "nope.xlsx")})
    assert res["error"]["code"] == "BANK_NOT_FOUND"


def test_dispatch_invalid_params(bank):
    res = dispatch("dictation.sample", {"bank": bank, "n": "abc"})
    assert res["error"]["code"] == "INVALID_PARAMS"


def test_dispatch_duplicate_batch_maps_to_code(bank):
    graded = [{"词条ID": "W0001", "我的答案": "incline"}]
    assert dispatch("grading.apply", {"bank": bank, "batch_id": "B1",
                                     "date": "2026-11-16", "graded": graded})["ok"]
    res = dispatch("grading.apply", {"bank": bank, "batch_id": "B1",
                                     "date": "2026-11-16", "graded": graded})
    assert res["error"]["code"] == "DUPLICATE_BATCH"


def test_call_json_wrapper(bank):
    res = call_json({"action": "bank.list_items", "params": {"bank": bank, "limit": 2}})
    assert res["ok"] and res["data"]["count"] == 2


def test_env_var_bank(monkeypatch, bank):
    monkeypatch.setenv("VOCAB_DICTATION_BANK", bank)
    res = dispatch("bank.stats", {})
    assert res["ok"] and res["data"]["词条总数"] == 7


def test_facade_roundtrip(bank, tmp_path):
    from vocab_dictation import expand_slash

    vd = VocabDictation(bank, workdir=str(tmp_path))
    assert vd.stats()["词条总数"] == 7
    items = vd.shuffle_all(seed=11)
    batch = vd.next_batch_id("2026-11-16")
    assert batch == "D20261116-01"
    # 斜杠同义词要写其中一支，直接照抄“a/b”不是合法答案
    graded = [{"词条ID": it["词条ID"], "我的答案": expand_slash(it["英文"])[0]}
              for it in items]
    preview = vd.preview(graded, batch_id=batch, date="2026-11-16")
    assert preview["得分"] == 7.0


def test_facade_raises_tool_error(tmp_path):
    vd = VocabDictation(str(tmp_path / "missing.xlsx"))
    with pytest.raises(ToolError) as ei:
        vd.stats()
    assert ei.value.code == "BANK_NOT_FOUND"
