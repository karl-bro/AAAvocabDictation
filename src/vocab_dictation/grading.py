# -*- coding: utf-8 -*-
"""批改层：预判（只读）与正式批改（写回词库统计、错题本、听写记录）。"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from openpyxl import load_workbook

from .bank import (BANK_COLS, LOG_COLS, SHEET_BANK, SHEET_LOG, SHEET_WRONG,
                   WRONG_COLS, BankError, DuplicateBatch, _apply_row_style,
                   read_sheet)
from .core import ERR_NONE, is_key_item, judge


def _normalize_graded(graded: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, g in enumerate(graded, 1):
        if not isinstance(g, Mapping):
            raise BankError(f"第 {i} 题批改项不是对象")
        wid = g.get("词条ID")
        if not wid:
            raise BankError(f"第 {i} 题缺少 词条ID")
        out.append({
            "词条ID": str(wid),
            "我的答案": g.get("我的答案") or "",
            "override": g.get("override") or None,
        })
    if not out:
        raise BankError("graded 为空，至少需要一题")
    return out


def _score_one(g: Mapping[str, Any], item: Mapping[str, Any]) -> tuple[float, str, str]:
    o = g.get("override")
    if o:
        return float(o.get("得分", 0)), o.get("错误类型", ERR_NONE), o.get("批注", "")
    return judge(g.get("我的答案"), item)


def _build_result(batch_id: str, date: str, scope: str, graded: list[dict[str, Any]],
                  bank: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    results, total, full, key_total, key_correct = [], 0.0, 0, 0, 0
    counter: dict[str, int] = {}
    for qno, g in enumerate(graded, 1):
        item = bank[g["词条ID"]]
        score, etype, comment = _score_one(g, item)
        total += score
        full += 1 if score == 1 else 0
        if is_key_item(item):
            key_total += 1
            key_correct += 1 if score == 1 else 0
        if etype:
            counter[etype] = counter.get(etype, 0) + 1
        results.append({
            "题号": qno, "词条ID": item["词条ID"], "标记": item["标记"],
            "类型": item["类型"], "中文释义": item["中文释义"],
            "英文": item["英文"], "我的答案": g.get("我的答案") or "",
            "得分": score, "错误类型": etype, "批注": comment,
        })
    n = len(graded)
    return {
        "批次ID": batch_id, "日期": date, "范围": scope, "题数": n,
        "得分": round(total, 1), "满分": float(n),
        "正确率": round(full / n, 4),          # 满分率（与历史报表口径一致）
        "平均得分率": round(total / n, 4),      # 按 0.5 折算的真实得分率
        "满分题数": full, "错题数": n - full,
        "重点题数": key_total, "重点正确数": key_correct,
        "错因统计": counter, "明细": results,
    }


def preview_grading(path: str, batch_id: str, date: str, scope: str,
                    graded: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """只判分不写库，供"先给结论、后落库"的两步式调用。"""
    g = _normalize_graded(graded)
    wb = load_workbook(path)
    bank = {r["词条ID"]: r for r in read_sheet(wb[SHEET_BANK], BANK_COLS)}
    missing = [x["词条ID"] for x in g if x["词条ID"] not in bank]
    if missing:
        raise BankError(f"词条ID 不在词库中：{missing[:10]}"
                        f"{'…' if len(missing) > 10 else ''}")
    return _build_result(batch_id, date, scope, g, bank)


def apply_grading(path: str, batch_id: str, date: str, scope: str,
                  graded: Iterable[Mapping[str, Any]], note: str = "",
                  allow_duplicate: bool = False) -> dict[str, Any]:
    """正式批改：判分 + 更新总词库统计 + 写错题本 + 写听写记录 + 自动摘帽。

    :param graded: ``[{"词条ID": "W0001", "我的答案": "liability", "override": {...}}]``
                   顺序即听写题号；``override`` 可强制指定得分/错误类型/批注。
    :param allow_duplicate: 默认 False，同一 ``batch_id`` 已存在听写记录时报错，
                   防止重复批改把统计写花。
    """
    g = _normalize_graded(graded)

    wb = load_workbook(path)
    if not allow_duplicate and any(str(r["批次ID"]) == str(batch_id)
                                   for r in read_sheet(wb[SHEET_LOG], LOG_COLS)):
        raise DuplicateBatch(
            f"批次 {batch_id} 已批改过；如需重批请改用新批次号或 allow_duplicate=true")

    bws, wws, lws = wb[SHEET_BANK], wb[SHEET_WRONG], wb[SHEET_LOG]
    bank = {r["词条ID"]: r for r in read_sheet(bws, BANK_COLS)}
    missing = [x["词条ID"] for x in g if x["词条ID"] not in bank]
    if missing:
        raise BankError(f"词条ID 不在词库中：{missing[:10]}"
                        f"{'…' if len(missing) > 10 else ''}")
    max_wrong = max((int(r["错题ID"][1:]) for r in read_sheet(wws, WRONG_COLS)
                     if re.match(r"E\d+$", str(r["错题ID"]))), default=0)

    result = _build_result(batch_id, date, scope, g, bank)

    for d, item in zip(result["明细"], (bank[x["词条ID"]] for x in g)):
        score, etype = d["得分"], d["错误类型"]
        r = item["_row"]
        bws.cell(r, 10).value = int(item["听写次数"] or 0) + 1
        bws.cell(r, 14).value = date
        if score == 1:
            bws.cell(r, 11).value = int(item["正确次数"] or 0) + 1
            streak = int(item["连续正确"] or 0) + 1
            bws.cell(r, 13).value = streak
            if streak >= 2:
                bws.cell(r, 9).value = "已掌握"
            elif bws.cell(r, 9).value == "未听写":
                bws.cell(r, 9).value = "学习中"
        else:
            bws.cell(r, 12).value = int(item["错误次数"] or 0) + 1
            bws.cell(r, 13).value = 0
            bws.cell(r, 9).value = "学习中"
            max_wrong += 1
            wws.append([f"E{max_wrong:04d}", item["词条ID"], item["英文"],
                        item["中文释义"], item["标记"], batch_id, date, etype,
                        d["我的答案"] or "", item["英文"], "待复习", 0, ""])
            _apply_row_style(wws, wws.max_row, len(WRONG_COLS))

    # 错题连续 2 次满分 → 摘帽（直接读单元格最新值，避免快照过期）
    id_to_row = {bws.cell(r, 1).value: r
                 for r in range(2, bws.max_row + 1) if bws.cell(r, 1).value}
    for w in read_sheet(wws, WRONG_COLS):
        if w["状态"] != "已摘帽" and w["词条ID"] in id_to_row:
            streak = int(bws.cell(id_to_row[w["词条ID"]], 13).value or 0)
            if streak >= 2:
                wws.cell(w["_row"], 11).value = "已摘帽"
                wws.cell(w["_row"], 13).value = date

    n = result["题数"]
    lws.append([batch_id, date, scope, n, result["得分"],
                round(result["满分题数"] / n, 4) if n else 0,
                result["错题数"], result["重点题数"], result["重点正确数"], note])
    _apply_row_style(lws, lws.max_row, len(LOG_COLS))
    lws.cell(lws.max_row, 6).number_format = "0.0%"
    wb.save(path)
    result["已写入"] = True
    return result
