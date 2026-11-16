# -*- coding: utf-8 -*-
"""统一调用入口：一个 ``dispatch(action, params)`` 走完全部能力。

设计要点
--------
* 输入输出都是纯 JSON（dict/list/str/number/bool），不含二进制、不含对象引用，
  因此任何语言的 LLM 应用（HTTP、MCP、函数调用）都能直接桥接。
* 每个动作的元数据集中在 ``ACTION_SPECS``，``capabilities()`` 会把它们转成
  JSON Schema，便于模型自我发现参数，无需额外文档。
* 失败也返回结构化错误码，调用方可据此分支重试或向用户提示。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Mapping

from .bank import BankError, BankExists, BankNotFound, DuplicateBatch

VERSION = "1.0.0"
BANK_ENV = "VOCAB_DICTATION_BANK"


class ToolError(Exception):
    """带错误码的可序列化异常。"""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


# ---------------- 动作元数据 ----------------

ACTION_SPECS: dict[str, dict[str, Any]] = {
    "skill.capabilities": {
        "summary": "列出全部可用动作及参数 JSON Schema，供模型自省。",
        "params": {},
        "returns": "动作清单",
    },
    "bank.init": {
        "summary": "创建空词库（四张表：使用说明/总词库/错题本/听写记录）。",
        "params": {
            "path": {"type": "string", "required": True, "desc": "词库 xlsx 绝对路径"},
            "overwrite": {"type": "boolean", "default": False, "desc": "已存在时是否重建"},
        },
        "returns": "path",
    },
    "bank.add_items": {
        "summary": "词条入库，自动编号；同来源+序号+英文自动去重。",
        "params": {
            "source": {"type": "string", "required": True, "desc": "来源页标识，如 v.L5-p1"},
            "date": {"type": "string", "desc": "入库日期 YYYY-MM-DD，默认今天"},
            "items": {"type": "array", "required": True,
                      "desc": "[{序号,类型,英文,词性,中文释义,标记,等号链,备注}]"},
        },
        "returns": "added / skipped / total",
    },
    "bank.list_items": {
        "summary": "按英文/中文、来源、状态、标记、类型筛选词条。",
        "params": {
            "query": {"type": "string", "desc": "英文或中文包含匹配"},
            "source": {"type": "string"},
            "status": {"type": "string", "enum": ["未听写", "学习中", "已掌握"]},
            "mark": {"type": "string", "enum": ["普通", "熟词僻义", "重点词"]},
            "item_type": {"type": "string", "enum": ["主词", "扩展词", "词组"]},
            "limit": {"type": "integer"},
        },
        "returns": "词条数组",
    },
    "bank.update_item": {
        "summary": "就地修改单个词条的可编辑字段（不触碰统计列）。",
        "params": {
            "item_id": {"type": "string", "required": True, "desc": "词条ID，如 W1287"},
            "fields": {"type": "object", "required": True,
                       "desc": "可改：英文/中文释义/词性/标记/等号链/备注/状态/类型"},
        },
        "returns": "changed / item",
    },
    "bank.stats": {
        "summary": "词库概览：总量、状态/标记/类型分布、错题、最近批次。",
        "params": {},
        "returns": "统计对象",
    },
    "dictation.batch_id": {
        "summary": "按当天已有批次推出下一个批次号 DYYYYMMDD-NN。",
        "params": {"date": {"type": "string", "desc": "YYYY-MM-DD，默认今天"}},
        "returns": "批次号字符串",
    },
    "dictation.sample": {
        "summary": "错题优先 + 分层随机抽样，返回打乱后的听写顺序。",
        "params": {
            "n": {"type": "integer", "required": True, "desc": "题量"},
            "scope": {"type": "object",
                      "desc": "{来源:[...], 类型:[...], 标记:[...], 序号区间:[lo,hi], 序号集合:[...]}"},
            "seed": {"type": "integer", "desc": "复现用随机种子"},
            "wrong_ratio": {"type": "number", "default": 0.6, "desc": "错题最多占比"},
        },
        "returns": "词条数组（顺序即题号）",
    },
    "dictation.shuffle_all": {
        "summary": "范围内全量词条打乱，不补词、不优先错题（“全量出卷”）。",
        "params": {"scope": {"type": "object"}, "seed": {"type": "integer"}},
        "returns": "词条数组",
    },
    "dictation.build_pdf": {
        "summary": "生成听写卷双版本（填空版 + 答案版），返回路径并自检。",
        "params": {
            "items": {"type": "array", "required": True, "desc": "词条数组，顺序即题号"},
            "meta": {"type": "object", "required": True, "desc": "{批次ID,日期,范围,说明?}"},
            "outdir": {"type": "string", "required": True},
            "prefix": {"type": "string", "desc": "文件名前缀，默认 听写_<日期>"},
        },
        "returns": "cloze / answer / verify",
    },
    "grading.preview": {
        "summary": "只判分不写库（两步式调用的第一步）。",
        "params": {
            "batch_id": {"type": "string", "required": True},
            "date": {"type": "string"},
            "scope": {"type": "string"},
            "graded": {"type": "array", "required": True,
                       "desc": "[{词条ID,我的答案,override?}]，顺序即题号"},
        },
        "returns": "得分/正确率/错因统计/逐题明细",
    },
    "grading.apply": {
        "summary": "正式批改：判分并写回总词库统计、错题本、听写记录（含自动摘帽）。",
        "params": {
            "batch_id": {"type": "string", "required": True},
            "date": {"type": "string"},
            "scope": {"type": "string"},
            "graded": {"type": "array", "required": True},
            "note": {"type": "string"},
            "allow_duplicate": {"type": "boolean", "default": False},
        },
        "returns": "同 preview，且 已写入=true",
    },
    "report.build": {
        "summary": "把批改结果渲染成 PDF 报告并自检。",
        "params": {
            "result": {"type": "object", "desc": "grading.apply/preview 的返回"},
            "result_path": {"type": "string", "desc": "或改为读取 JSON 文件"},
            "out": {"type": "string", "required": True},
        },
        "returns": "path / verify",
    },
    "submission.prepare": {
        "summary": "完成稿照片纠偏、分页、增强（需 image 可选依赖）。",
        "params": {
            "images": {"type": "array", "required": True, "desc": "照片路径列表"},
            "outdir": {"type": "string", "required": True},
        },
        "returns": "页数/页面/警告",
    },
}


def _json_schema(action: str) -> dict[str, Any]:
    spec = ACTION_SPECS[action]
    props = {
        "bank": {"type": "string", "description": "词库 xlsx 路径（可省略，取默认或环境变量）"},
    }
    required = []
    for name, p in spec["params"].items():
        node: dict[str, Any] = {"type": p.get("type", "string")}
        if "enum" in p:
            node["enum"] = p["enum"]
        if "default" in p:
            node["default"] = p["default"]
        if p.get("desc"):
            node["description"] = p["desc"]
        props[name] = node
        if p.get("required"):
            required.append(name)
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


def capabilities() -> dict[str, Any]:
    """机器可读的能力清单：动作名、说明、参数 JSON Schema、返回说明。"""
    return {
        "skill": "vocab-dictation",
        "version": VERSION,
        "protocol": "json-envelope/v1",
        "description": "考研生词本听写闭环：识别清单入库、抽样出卷、批改统计、错题摘帽、报告输出。",
        "actions": [
            {"action": name, "summary": spec["summary"],
             "returns": spec["returns"], "input_schema": _json_schema(name)}
            for name, spec in ACTION_SPECS.items()
        ],
    }


# ---------------- 参数校验 ----------------

def _resolve_bank(params: Mapping[str, Any], bank: str | None) -> str:
    p = params.get("bank") or bank or os.environ.get(BANK_ENV)
    if not p:
        raise ToolError("BANK_REQUIRED",
                        f"未提供词库路径：请在参数 bank、构造参数或环境变量 {BANK_ENV} 中给出")
    return os.path.abspath(str(p))


def _need(params: Mapping[str, Any], *names: str) -> None:
    missing = [n for n in names if params.get(n) in (None, "", [])]
    if missing:
        raise ToolError("INVALID_PARAMS", f"缺少必填参数：{missing}",
                        {"missing": missing})


def _as_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ToolError("INVALID_PARAMS", f"参数 {name} 必须是整数，收到 {value!r}") from e


# ---------------- 动作实现 ----------------

def _do_init(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import init_bank
    path = p.get("path") or _resolve_bank(p, bank)
    return {"path": init_bank(path, overwrite=bool(p.get("overwrite", False)))}


def _do_add(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import add_items
    _need(p, "source", "items")
    if not isinstance(p["items"], list):
        raise ToolError("INVALID_PARAMS", "items 必须是数组")
    return add_items(_resolve_bank(p, bank), p["items"], p["source"], p.get("date"))


def _do_list(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import list_items
    rows = list_items(_resolve_bank(p, bank), query=p.get("query"),
                      source=p.get("source"), status=p.get("status"),
                      mark=p.get("mark"), item_type=p.get("item_type"),
                      limit=_as_int(p["limit"], "limit") if p.get("limit") else None)
    return {"count": len(rows), "items": rows}


def _do_update(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import update_item
    _need(p, "item_id", "fields")
    return update_item(_resolve_bank(p, bank), p["item_id"], p["fields"])


def _do_stats(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import bank_stats
    return bank_stats(_resolve_bank(p, bank))


def _do_batch_id(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import next_batch_id
    return {"batch_id": next_batch_id(_resolve_bank(p, bank), p.get("date"))}


def _do_sample(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import sample_items
    _need(p, "n")
    items = sample_items(_resolve_bank(p, bank), _as_int(p["n"], "n"),
                         scope=p.get("scope"), seed=p.get("seed"),
                         wrong_ratio=float(p.get("wrong_ratio", 0.6)))
    return {"count": len(items), "items": items}


def _do_shuffle(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .bank import shuffle_all
    items = shuffle_all(_resolve_bank(p, bank), scope=p.get("scope"), seed=p.get("seed"))
    return {"count": len(items), "items": items}


def _do_dictation_pdf(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .rendering import build_dictation_pdfs
    _need(p, "items", "meta", "outdir")
    items, meta = p["items"], p["meta"]
    if not isinstance(meta, Mapping) or "批次ID" not in meta or "日期" not in meta:
        raise ToolError("INVALID_PARAMS", "meta 必须包含 批次ID 与 日期")
    try:
        paths = build_dictation_pdfs(items, meta, p["outdir"],
                                     prefix=p.get("prefix"),
                                     bank_path=_resolve_bank(p, bank) if (p.get("bank") or bank) else None)
    except AssertionError as e:
        raise ToolError("RENDER_FAILED", str(e)) from e
    return paths


def _do_preview(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .grading import preview_grading
    from .bank import BankError
    _need(p, "batch_id", "graded")
    try:
        return preview_grading(_resolve_bank(p, bank), p["batch_id"],
                               p.get("date") or _today(), p.get("scope", ""), p["graded"])
    except BankError as e:
        raise _map_bank_error(e) from e


def _do_apply(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .grading import apply_grading
    from .bank import BankError
    _need(p, "batch_id", "graded")
    try:
        return apply_grading(_resolve_bank(p, bank), p["batch_id"],
                             p.get("date") or _today(), p.get("scope", ""),
                             p["graded"], note=p.get("note", ""),
                             allow_duplicate=bool(p.get("allow_duplicate", False)))
    except BankError as e:
        raise _map_bank_error(e) from e


def _do_report(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .rendering import build_report_pdf
    _need(p, "out")
    result = p.get("result")
    if result is None:
        _need(p, "result_path")
        with open(p["result_path"], encoding="utf-8") as f:
            result = json.load(f)
    if not isinstance(result, Mapping) or "明细" not in result:
        raise ToolError("INVALID_PARAMS", "result 不是有效批改结果（缺少 明细）")
    try:
        return build_report_pdf(result, p["out"])
    except AssertionError as e:
        raise ToolError("RENDER_FAILED", str(e)) from e


def _do_prepare(p: Mapping[str, Any], bank: str | None) -> dict[str, Any]:
    from .prepare import prepare_submission
    _need(p, "images", "outdir")
    if not isinstance(p["images"], list):
        raise ToolError("INVALID_PARAMS", "images 必须是路径数组")
    return prepare_submission(p["images"], p["outdir"])


def _today() -> str:
    import datetime as dt
    return dt.date.today().isoformat()


def _map_bank_error(e: Exception) -> ToolError:
    if isinstance(e, BankNotFound):
        return ToolError("BANK_NOT_FOUND", str(e))
    if isinstance(e, BankExists):
        return ToolError("BANK_EXISTS", str(e))
    if isinstance(e, DuplicateBatch):
        return ToolError("DUPLICATE_BATCH", str(e))
    return ToolError("BANK_ERROR", str(e))


_HANDLERS: dict[str, Callable[[Mapping[str, Any], str | None], dict[str, Any]]] = {
    "bank.init": _do_init,
    "bank.add_items": _do_add,
    "bank.list_items": _do_list,
    "bank.update_item": _do_update,
    "bank.stats": _do_stats,
    "dictation.batch_id": _do_batch_id,
    "dictation.sample": _do_sample,
    "dictation.shuffle_all": _do_shuffle,
    "dictation.build_pdf": _do_dictation_pdf,
    "grading.preview": _do_preview,
    "grading.apply": _do_apply,
    "report.build": _do_report,
    "submission.prepare": _do_prepare,
}


def dispatch(action: str, params: Mapping[str, Any] | None = None,
             bank: str | None = None) -> dict[str, Any]:
    """统一入口：执行一个动作并返回标准信封。

    >>> dispatch("bank.stats", {"bank": "vocab.xlsx"})["ok"]
    True
    """
    t0 = time.time()
    params = dict(params or {})
    envelope: dict[str, Any] = {
        "ok": False, "action": action, "version": VERSION,
        "data": None, "warnings": [], "error": None,
        "meta": {"elapsed_ms": 0, "bank": params.get("bank") or bank},
    }

    try:
        if action == "skill.capabilities":
            envelope["data"] = capabilities()
            envelope["ok"] = True
        else:
            handler = _HANDLERS.get(action)
            if handler is None:
                raise ToolError("INVALID_ACTION",
                                f"未知动作：{action}",
                                {"available": sorted(list(ACTION_SPECS))})
            envelope["data"] = handler(params, bank)
            envelope["ok"] = True
            for w in _collect_warnings(envelope["data"]):
                envelope["warnings"].append(w)
    except ToolError as e:
        envelope["error"] = {"code": e.code, "message": e.message,
                             "details": e.details}
    except BankError as e:
        mapped = _map_bank_error(e)
        envelope["error"] = {"code": mapped.code, "message": mapped.message,
                             "details": {}}
    except FileNotFoundError as e:
        envelope["error"] = {"code": "FILE_NOT_FOUND", "message": str(e), "details": {}}
    except Exception as e:  # 兜底，保证调用方永远拿到 JSON
        envelope["error"] = {"code": "INTERNAL_ERROR",
                             "message": f"{type(e).__name__}: {e}", "details": {}}
    envelope["meta"]["elapsed_ms"] = int((time.time() - t0) * 1000)
    return envelope


def _collect_warnings(data: Any) -> list[str]:
    """从结果里提取可展示的警告（命中就提示，不改变主流程）。"""
    if isinstance(data, Mapping):
        out = []
        if data.get("警告"):
            out.extend([str(x) for x in data["警告"]])
        if data.get("skipped"):
            out.append(f"去重跳过 {len(data['skipped'])} 条重复词条")
        if data.get("verify") not in (None, "OK"):
            out.append(f"自检结果 {data['verify']}")
        return out
    return []


def call_json(payload: Mapping[str, Any], bank: str | None = None) -> dict[str, Any]:
    """接收完整请求体 ``{"action":..., "params":{...}}`` 的便捷包装。"""
    return dispatch(payload.get("action", ""), payload.get("params") or {}, bank)
