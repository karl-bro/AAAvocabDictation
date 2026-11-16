# -*- coding: utf-8 -*-
"""从 ``ACTION_SPECS`` 生成各协议的工具声明，保证 schema 与实现永不分叉。

    python scripts/export_tool_schemas.py

输出：
* schemas/tool.openai.json      —— OpenAI function calling 的 function 定义
* schemas/tool.anthropic.json   —— Anthropic Messages API 的 tool 定义
* schemas/capabilities.json     —— 能力清单快照（供离线查阅/版本比对）
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from vocab_dictation import VERSION, capabilities  # noqa: E402
from vocab_dictation.api import ACTION_SPECS  # noqa: E402

TOOL_NAME = "vocab_dictation"
SCHEMAS = REPO / "schemas"


def _required(spec: dict) -> list[str]:
    return [k for k, v in spec["params"].items() if v.get("required")]


def action_menu() -> str:
    lines = []
    for name, spec in ACTION_SPECS.items():
        req = _required(spec)
        opt = [k for k in spec["params"] if k not in req]
        bits = []
        if req:
            bits.append("必填 " + ",".join(req))
        if opt:
            bits.append("可选 " + ",".join(opt))
        lines.append(f"- {name}：{spec['summary']}" + ("（" + "；".join(bits) + "）" if bits else ""))
    return "\n".join(lines)


def build_parameters() -> dict:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTION_SPECS),
                       "description": "要执行的动作，具体参数见 capabilities 的 input_schema"},
            "params": {"type": "object", "additionalProperties": True,
                       "description": "动作参数；除 bank 外的字段都放这里"},
            "bank": {"type": "string",
                     "description": "词库 xlsx 路径；也可由服务端环境变量 VOCAB_DICTATION_BANK 提供"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }


def main() -> None:
    SCHEMAS.mkdir(exist_ok=True)
    desc = ("考研英语生词本听写闭环：把生词本识别结果入库、按错题优先或全量打乱出卷、"
            "批改手写答案并按 1/0.5/0 三档评分、维护错题本与两次满分摘帽、生成 PDF 报告。\n"
            "返回统一 JSON 信封 {ok, action, version, data, warnings, error, meta}。\n"
            "动作清单：\n" + action_menu())

    params = build_parameters()
    (SCHEMAS / "tool.openai.json").write_text(json.dumps(
        {"type": "function",
         "function": {"name": TOOL_NAME, "description": desc, "parameters": params}},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    (SCHEMAS / "tool.anthropic.json").write_text(json.dumps(
        {"name": TOOL_NAME, "description": desc, "input_schema": params},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    (SCHEMAS / "capabilities.json").write_text(json.dumps(
        capabilities(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    for f in ("tool.openai.json", "tool.anthropic.json", "capabilities.json"):
        print(f"written schemas/{f}")


if __name__ == "__main__":
    main()
