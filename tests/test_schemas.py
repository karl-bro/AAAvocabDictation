# -*- coding: utf-8 -*-
"""守文档与代码不分叉：schema、skill.yaml、SKILL.md 的声明必须与实现一致。"""
import json
import re
from pathlib import Path

from vocab_dictation import dispatch
from vocab_dictation.api import ACTION_SPECS

REPO = Path(__file__).resolve().parent.parent


def _load(rel: str) -> dict:
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def test_request_schema_shape():
    req = _load("schemas/request.schema.json")
    assert req["type"] == "object"
    assert req["required"] == ["action"]
    assert set(req["properties"]) == {"action", "params", "bank"}


def test_response_schema_envelope():
    resp = _load("schemas/response.schema.json")
    assert set(resp["required"]) == {"ok", "action", "version", "data",
                                     "warnings", "error", "meta"}


def test_response_schema_covers_core_error_codes():
    resp = _load("schemas/response.schema.json")
    err = next(branch for branch in resp["properties"]["error"]["oneOf"]
               if branch.get("type") == "object")
    enum = set(err["properties"]["code"]["enum"])
    for code in ("INVALID_ACTION", "INVALID_PARAMS", "BANK_REQUIRED", "BANK_NOT_FOUND",
                 "BANK_EXISTS", "DUPLICATE_BATCH", "BANK_ERROR", "RENDER_FAILED",
                 "FILE_NOT_FOUND", "INTERNAL_ERROR"):
        assert code in enum, code


def test_generated_capabilities_in_sync():
    cap = _load("schemas/capabilities.json")
    assert {a["action"] for a in cap["actions"]} == set(ACTION_SPECS)


def test_generated_tool_declarations_in_sync():
    oa = _load("schemas/tool.openai.json")
    an = _load("schemas/tool.anthropic.json")
    enum = set(oa["function"]["parameters"]["properties"]["action"]["enum"])
    assert enum == set(ACTION_SPECS)
    assert an["input_schema"] == oa["function"]["parameters"]
    assert oa["function"]["name"] == an["name"] == "vocab_dictation"


def test_skill_yaml_actions_match_code():
    text = (REPO / "skill.yaml").read_text(encoding="utf-8")
    names = set(re.findall(r"^\s*-\s*name:\s*([\w.]+)$", text, re.M))
    assert names == set(ACTION_SPECS)


def test_skill_md_front_matter():
    text = (REPO / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "name: vocab-dictation" in fm
    assert "description:" in fm
    assert "version:" in fm


def test_envelope_matches_documented_keys(bank):
    ok = dispatch("bank.stats", {"bank": bank})
    assert set(ok) == {"ok", "action", "version", "data", "warnings", "error", "meta"}
    bad = dispatch("nope", {"bank": bank})
    assert set(bad) == {"ok", "action", "version", "data", "warnings", "error", "meta"}
    assert set(bad["error"]) == {"code", "message", "details"}


def test_readme_links_exist():
    for name in ("README.md", "README.zh-CN.md", "SKILL.md", "skill.yaml", "LICENSE",
                 "CHANGELOG.md", "CONTRIBUTING.md", "docs/quickstart.md",
                 "docs/api-reference.md", "docs/integration.md", "docs/scoring-rules.md",
                 "prompts/extract_items.md", "prompts/read_submission.md",
                 "assets/sample_items.json", "scripts/export_tool_schemas.py"):
        assert (REPO / name).exists(), name
