# -*- coding: utf-8 -*-
"""词库层：xlsx 词库的初始化、入库、查询、抽样与批次号。

工作簿固定四张表：``使用说明 / 总词库 / 错题本 / 听写记录``。
对外一律使用 JSON 可序列化的 dict，字段名与表头一致（中文列名即字段名），
这样调用方无需了解 xlsx 结构即可读写。
"""
from __future__ import annotations

import datetime as dt
import math
import os
import random
import re
from typing import Any, Iterable, Mapping, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .core import compact, is_key_item, norm_text

BANK_COLS = ["词条ID", "来源", "序号", "类型", "英文", "词性", "中文释义", "标记",
             "状态", "听写次数", "正确次数", "错误次数", "连续正确", "最近听写日期",
             "入库日期", "备注", "等号链"]
WRONG_COLS = ["错题ID", "词条ID", "英文", "中文释义", "标记", "批次ID", "听写日期",
              "错误类型", "我的答案", "正确答案", "状态", "连续正确", "摘帽日期"]
LOG_COLS = ["批次ID", "日期", "范围/来源", "抽查数量", "得分", "正确率", "错题数",
            "重点题数", "重点正确数", "备注"]

SHEET_INFO, SHEET_BANK, SHEET_WRONG, SHEET_LOG = "使用说明", "总词库", "错题本", "听写记录"

HEADER_FG = "1F4E79"
GRID_C = "B8C7D9"
MARK_COLORS = {"熟词僻义": "C00000", "重点词": "BF6F00", "普通": "404040"}

ITEM_TYPES = ("主词", "扩展词", "词组")
MARK_VALUES = ("普通", "熟词僻义", "重点词")
STATUS_VALUES = ("未听写", "学习中", "已掌握")

THIN = Side(style="thin", color=GRID_C)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


class BankError(Exception):
    """词库层错误基类。"""


class BankNotFound(BankError):
    pass


class BankExists(BankError):
    pass


class DuplicateBatch(BankError):
    pass


# ---------------- 样式与读取 ----------------

def _style_header(ws, ncols: int) -> None:
    fill = PatternFill("solid", fgColor=HEADER_FG)
    for c in range(1, ncols + 1):
        cell = ws.cell(1, c)
        cell.fill = fill
        cell.font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=10.5)
        cell.alignment = CENTER
        cell.border = BORDER
    ws.freeze_panes = "A2"


def _apply_row_style(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row, c)
        cell.border = BORDER
        cell.alignment = CENTER if c <= 4 or c in (9, 10, 11, 12, 13, 14, 15, 17) else WRAP
        cell.font = Font(name="微软雅黑", size=10)


def read_sheet(ws, cols: Sequence[str]) -> list[dict[str, Any]]:
    """把工作表读成 dict 列表，附带 ``_row`` 供写回定位。"""
    out = []
    for r in ws.iter_rows(min_row=2, max_col=len(cols)):
        if all(c.value in (None, "") for c in r):
            continue
        d = {cols[i]: r[i].value for i in range(len(cols))}
        d["_row"] = r[0].row
        out.append(d)
    return out


def _open_bank(path: str, write: bool = False):
    if not os.path.exists(path):
        raise BankNotFound(f"词库不存在：{path}")
    wb = load_workbook(path)
    for name in (SHEET_BANK, SHEET_WRONG, SHEET_LOG):
        if name not in wb.sheetnames:
            raise BankError(f"词库缺少工作表：{name}（请先 init 或修复文件）")
    return wb


# ---------------- 初始化 ----------------

def init_bank(path: str, overwrite: bool = False) -> str:
    """创建一个空词库；已存在时默认报错，避免误覆盖真实数据。"""
    if os.path.exists(path) and not overwrite:
        raise BankExists(f"词库已存在：{path}（如需重建请显式 overwrite=true）")

    wb = Workbook()
    info = wb.active
    info.title = SHEET_INFO
    lines = [
        ("考研生词听写 · 词库与错题本", True),
        ("", False),
        ("一、每日流程：", True),
        ("1. 上传当天生词本照片（可多页），告知抽查数量 N（可附范围，如“只抽1~10号”“只听主词”）。", False),
        ("2. 助手回传识别清单，你核对/纠正后再生成听写 PDF（填空版 + 答案版）。", False),
        ("3. 打印填空版手写答题，完成后拍照上传。", False),
        ("4. 助手批改并输出批改报告，错题自动进入错题本。", False),
        ("", False),
        ("二、标记规则：", True),
        ("黑色=主单词；蓝色=扩展词/扩展词组；红圈中文=熟词僻义；红色波浪线=重点词。", False),
        ("主词、扩展词、词组均为独立听写项；斜杠同义词算一项，写出任一即对。", False),
        ("", False),
        ("三、抽样与摘帽：", True),
        ("错题优先（错题最多占当次 60%），其余从新词/未掌握词中随机。", False),
        ("错题连续 2 次听写全对自动摘帽；再错则重新计数。", False),
        ("", False),
        ("四、评分：每题1分；小拼写失误（1~2个字母且可辨认）0.5分；严重错误、未答、词组漏词/错序 0 分。", False),
    ]
    for i, (text, bold) in enumerate(lines, 1):
        cell = info.cell(i, 1, text)
        cell.font = Font(name="微软雅黑", size=13 if i == 1 else 10.5, bold=bold,
                         color=HEADER_FG if i == 1 else "404040")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    info.column_dimensions["A"].width = 95
    info.sheet_view.showGridLines = False

    widths = {SHEET_BANK: [9, 9, 6, 8, 20, 7, 30, 9, 9, 9, 9, 9, 9, 12, 12, 26, 8],
              SHEET_WRONG: [9, 9, 20, 28, 9, 13, 12, 12, 20, 20, 9, 9, 12],
              SHEET_LOG: [13, 12, 22, 9, 7, 8, 8, 9, 10, 24]}
    for name, cols in ((SHEET_BANK, BANK_COLS), (SHEET_WRONG, WRONG_COLS),
                       (SHEET_LOG, LOG_COLS)):
        ws = wb.create_sheet(name)
        for c, h in enumerate(cols, 1):
            ws.cell(1, c, h)
        _style_header(ws, len(cols))
        for c, w in enumerate(widths[name], 1):
            ws.column_dimensions[get_column_letter(c)].width = w

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
    return os.path.abspath(path)


# ---------------- 入库 ----------------

def _validate_item(it: Mapping[str, Any], idx: int) -> dict[str, Any]:
    if not isinstance(it, Mapping):
        raise BankError(f"第 {idx} 个词条不是对象")
    for key in ("序号", "英文", "中文释义"):
        if it.get(key) in (None, ""):
            raise BankError(f"第 {idx} 个词条缺少必填字段：{key}")
    typ = it.get("类型") or "主词"
    if typ not in ITEM_TYPES:
        raise BankError(f"第 {idx} 个词条类型非法：{typ}（允许 {list(ITEM_TYPES)}）")
    mark = it.get("标记") or "普通"
    if mark not in MARK_VALUES:
        raise BankError(f"第 {idx} 个词条标记非法：{mark}（允许 {list(MARK_VALUES)}）")
    return {
        "序号": int(it["序号"]),
        "类型": typ,
        "英文": str(it["英文"]).strip(),
        "词性": it.get("词性") or "",
        "中文释义": str(it["中文释义"]).strip(),
        "标记": mark,
        "备注": it.get("备注") or "",
        "等号链": it.get("等号链") or "",
    }


def add_items(path: str, items: Iterable[Mapping[str, Any]],
              source: str, date: str | None = None) -> dict[str, Any]:
    """入库并自动编号；同 ``来源+序号+英文`` 视为重复，自动跳过。

    :return: ``{"added": [词条ID...], "skipped": [...], "total": n}``
    """
    if not source:
        raise BankError("source 不能为空（形如 n.2-p1，用于去重与按页抽样）")
    date = date or dt.date.today().isoformat()

    norm_items = [_validate_item(it, i) for i, it in enumerate(items, 1)]
    if not norm_items:
        return {"added": [], "skipped": [], "total": 0, "ids": []}

    wb = _open_bank(path, write=True)
    ws = wb[SHEET_BANK]
    existing = read_sheet(ws, BANK_COLS)
    dup_keys = {(r["来源"], r["序号"], compact(r["英文"])) for r in existing}
    max_id = max((int(r["词条ID"][1:]) for r in existing
                  if re.match(r"W\d+$", str(r["词条ID"]))), default=0)

    added, skipped = [], []
    for it in norm_items:
        key = (source, it["序号"], compact(it["英文"]))
        if key in dup_keys:
            skipped.append({"序号": it["序号"], "英文": it["英文"], "reason": "duplicate"})
            continue
        dup_keys.add(key)
        max_id += 1
        wid = f"W{max_id:04d}"
        ws.append([wid, source, it["序号"], it["类型"], it["英文"], it["词性"],
                   it["中文释义"], it["标记"], "未听写", 0, 0, 0, 0, "", date,
                   it["备注"], it["等号链"]])
        r = ws.max_row
        _apply_row_style(ws, r, len(BANK_COLS))
        mark = ws.cell(r, 8)
        mark.font = Font(name="微软雅黑", size=10, bold=True,
                         color=MARK_COLORS.get(it["标记"], "404040"))
        added.append(wid)

    wb.save(path)
    return {"added": added, "skipped": skipped, "total": len(existing) + len(added),
            "ids": added}


# ---------------- 查询与就地修改 ----------------

def list_items(path: str, *, query: str | None = None, source: str | None = None,
               status: str | None = None, mark: str | None = None,
               item_type: str | None = None, limit: int | None = None,
               with_row: bool = False) -> list[dict[str, Any]]:
    """按条件筛选词条；``query`` 对英文/中文释义做包含匹配。"""
    wb = _open_bank(path)
    rows = read_sheet(wb[SHEET_BANK], BANK_COLS)
    if source:
        rows = [r for r in rows if r["来源"] == source]
    if status:
        rows = [r for r in rows if r["状态"] == status]
    if mark:
        rows = [r for r in rows if r["标记"] == mark]
    if item_type:
        rows = [r for r in rows if r["类型"] == item_type]
    if query:
        q = norm_text(query)
        rows = [r for r in rows
                if q in norm_text(r["英文"]) or q in norm_text(r["中文释义"] or "")]
    if limit:
        rows = rows[:int(limit)]
    if not with_row:
        rows = [{k: v for k, v in r.items() if k != "_row"} for r in rows]
    return rows


def update_item(path: str, item_id: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """就地修改单个词条的可编辑字段，不触碰统计列与整行样式。"""
    editable = {"英文", "中文释义", "词性", "标记", "等号链", "备注", "状态", "类型"}
    unknown = set(fields) - editable
    if unknown:
        raise BankError(f"不支持修改字段：{sorted(unknown)}（可改 {sorted(editable)}）")

    wb = _open_bank(path, write=True)
    ws = wb[SHEET_BANK]
    ci = {c.value: i + 1 for i, c in enumerate(ws[1])}
    rows = read_sheet(ws, BANK_COLS)
    target = next((r for r in rows if r["词条ID"] == item_id), None)
    if target is None:
        raise BankError(f"词条不存在：{item_id}")

    if "类型" in fields and fields["类型"] not in ITEM_TYPES:
        raise BankError(f"类型非法：{fields['类型']}")
    if "标记" in fields and fields["标记"] not in MARK_VALUES:
        raise BankError(f"标记非法：{fields['标记']}")
    if "状态" in fields and fields["状态"] not in STATUS_VALUES:
        raise BankError(f"状态非法：{fields['状态']}")

    changed = []
    for k, v in fields.items():
        ws.cell(target["_row"], ci[k]).value = v
        changed.append(k)
    wb.save(path)
    out = {k: v for k, v in target.items() if k != "_row"}
    out.update(fields)
    return {"词条ID": item_id, "changed": changed, "item": out}


# ---------------- 抽样 ----------------

def _in_scope(item: Mapping[str, Any], scope: Mapping[str, Any] | None) -> bool:
    if not scope:
        return True
    if scope.get("来源") and item["来源"] not in scope["来源"]:
        return False
    if scope.get("类型") and item["类型"] not in scope["类型"]:
        return False
    if scope.get("标记") and item["标记"] not in scope["标记"]:
        return False
    if scope.get("序号区间"):
        lo, hi = scope["序号区间"]
        if not (lo <= int(item["序号"]) <= hi):
            return False
    if scope.get("序号集合") and int(item["序号"]) not in scope["序号集合"]:
        return False
    return True


def sample_items(path: str, n: int, scope: Mapping[str, Any] | None = None,
                 seed: Any = None, wrong_ratio: float = 0.6) -> list[dict[str, Any]]:
    """错题优先 + 分层随机抽样，返回打乱后的词条列表（顺序即听写顺序）。

    分层次序：未听写的熟僻/重点 → 未听写普通 → 学习中 → 已掌握。
    ``wrong_ratio`` 控制错题最多占比（默认 0.6，与技能口径一致）。
    """
    if n <= 0:
        raise BankError("n 必须为正整数")
    rng = random.Random(seed)
    wb = _open_bank(path)
    bank = read_sheet(wb[SHEET_BANK], BANK_COLS)
    wrong = read_sheet(wb[SHEET_WRONG], WRONG_COLS)
    pool = [r for r in bank if _in_scope(r, scope)]
    by_id = {r["词条ID"]: r for r in bank}

    active_wrong_ids, seen = [], set()
    for w in wrong:
        wid = w["词条ID"]
        if w["状态"] != "已摘帽" and wid in by_id and wid not in seen:
            if by_id[wid] in pool:
                active_wrong_ids.append(wid)
                seen.add(wid)

    def sort_key(wid):
        r = by_id[wid]
        return (-int(r["错误次数"] or 0), str(r["最近听写日期"] or ""), rng.random())

    active_wrong_ids.sort(key=sort_key)
    wrong_quota = min(len(active_wrong_ids), math.ceil(n * wrong_ratio))
    picked = active_wrong_ids[:wrong_quota]

    rest = [r for r in pool if r["词条ID"] not in set(picked)]
    groups = [
        [r for r in rest if r["状态"] == "未听写" and is_key_item(r)],
        [r for r in rest if r["状态"] == "未听写" and not is_key_item(r)],
        [r for r in rest if r["状态"] == "学习中"],
        [r for r in rest if r["状态"] == "已掌握"],
    ]
    for g in groups:
        rng.shuffle(g)
        for r in g:
            if len(picked) >= n:
                break
            picked.append(r["词条ID"])
        if len(picked) >= n:
            break

    chosen = [by_id[i] for i in picked[:n]]
    rng.shuffle(chosen)
    return [{k: r.get(k) for k in BANK_COLS} for r in chosen]


def shuffle_all(path: str, scope: Mapping[str, Any] | None = None,
                seed: Any = None) -> list[dict[str, Any]]:
    """把范围内全部词条打乱（不做错题优先、不补词），用于"全量听写"。"""
    rng = random.Random(seed)
    wb = _open_bank(path)
    pool = [r for r in read_sheet(wb[SHEET_BANK], BANK_COLS) if _in_scope(r, scope)]
    rng.shuffle(pool)
    return [{k: r.get(k) for k in BANK_COLS} for r in pool]


# ---------------- 批次与统计 ----------------

def next_batch_id(path: str, date: str | None = None) -> str:
    """生成当天批次号 DYYYYMMDD-NN；出卷不写听写记录，同日多批次需人工指定序号。"""
    date = date or dt.date.today().isoformat()
    wb = _open_bank(path)
    logs = read_sheet(wb[SHEET_LOG], LOG_COLS)
    ymd = date.replace("-", "")
    seq = max((int(str(r["批次ID"]).split("-")[1]) for r in logs
               if str(r["批次ID"]).startswith(f"D{ymd}-")), default=0) + 1
    return f"D{ymd}-{seq:02d}"


def batch_exists(path: str, batch_id: str) -> bool:
    """该批次是否已写过听写记录（用于防止重复批改）。"""
    wb = _open_bank(path)
    return any(str(r["批次ID"]) == str(batch_id)
               for r in read_sheet(wb[SHEET_LOG], LOG_COLS))


def bank_stats(path: str) -> dict[str, Any]:
    """词库概览：词条总量、状态/标记/类型分布、链成员、错题与最近批次。"""
    wb = _open_bank(path)
    bank = read_sheet(wb[SHEET_BANK], BANK_COLS)
    wrong = read_sheet(wb[SHEET_WRONG], WRONG_COLS)
    logs = read_sheet(wb[SHEET_LOG], LOG_COLS)

    def count(rows, key):
        out: dict[str, int] = {}
        for r in rows:
            k = r.get(key) or "（空）"
            out[str(k)] = out.get(str(k), 0) + 1
        return out

    return {
        "词条总数": len(bank),
        "按状态": count(bank, "状态"),
        "按标记": count(bank, "标记"),
        "按类型": count(bank, "类型"),
        "等号链成员": sum(1 for r in bank if r["等号链"] == "是"),
        "错题总数": len(wrong),
        "待复习错题": sum(1 for w in wrong if w["状态"] != "已摘帽"),
        "已摘帽错题": sum(1 for w in wrong if w["状态"] == "已摘帽"),
        "听写批次数": len(logs),
        "最近批次": [{"批次ID": r["批次ID"], "日期": str(r["日期"]),
                      "得分": r["得分"], "正确率": r["正确率"]} for r in logs[-5:]],
        "最近听写日期": max((str(r["最近听写日期"]) for r in bank
                          if r["最近听写日期"]), default=None),
    }
