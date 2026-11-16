# -*- coding: utf-8 -*-
"""批改层测试：预判只读、正式写库、重复批次保护、连续两次摘帽。"""
import pytest
from openpyxl import load_workbook

from vocab_dictation.bank import (SHEET_BANK, SHEET_LOG, SHEET_WRONG, bank_stats,
                                  list_items)
from vocab_dictation.grading import apply_grading, preview_grading

DATE = "2026-11-16"

# 7 题：6 对 1 错（incline 写错）、1 组词组半对场景
GRADED_MIXED = [
    {"词条ID": "W0001", "我的答案": "indine"},          # 0.5 拼写
    {"词条ID": "W0002", "我的答案": "indine to do sth"},  # 0 词组漏词
    {"词条ID": "W0003", "我的答案": "deem"},
    {"词条ID": "W0004", "我的答案": "selective course"},
    {"词条ID": "W0005", "我的答案": "hinder"},
    {"词条ID": "W0006", "我的答案": "hamper"},
    {"词条ID": "W0007", "我的答案": ""},                # 0 未作答
]

GRADED_ALL_RIGHT = [
    {"词条ID": "W0001", "我的答案": "incline"},
    {"词条ID": "W0002", "我的答案": "incline to do sth"},
    {"词条ID": "W0003", "我的答案": "deem"},
    {"词条ID": "W0004", "我的答案": "optional course"},
    {"词条ID": "W0005", "我的答案": "hinder"},
    {"词条ID": "W0006", "我的答案": "hamper"},
    {"词条ID": "W0007", "我的答案": "lay off"},
]


def test_preview_does_not_write(bank):
    res = preview_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED)
    assert res["得分"] == 4.5 and res["满分"] == 7.0
    assert res["正确率"] == round(4 / 7, 4)
    assert res["平均得分率"] == round(4.5 / 7, 4)
    assert res["错题数"] == 3                     # 半对也算一次错误
    assert res["错因统计"] == {"拼写错误": 1, "词组漏词": 1, "未作答": 1}

    stats = bank_stats(bank)
    assert stats["听写批次数"] == 0               # 未写听写记录
    assert list_items(bank, query="incline")[0]["听写次数"] == 0
    assert stats["错题总数"] == 0


def test_apply_writes_stats_wrongbook_and_log(bank):
    res = apply_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED)
    assert res["已写入"] is True

    wb = load_workbook(bank)
    log = wb[SHEET_LOG]
    assert log.max_row == 2
    assert [c.value for c in log[2]][:5] == ["D20261116-01", DATE, "t.L1 p1", 7, 4.5]

    wrong = wb[SHEET_WRONG]
    assert wrong.max_row - 1 == 3                 # 3 条错题（含半对）
    ids = [wrong.cell(r, 1).value for r in range(2, wrong.max_row + 1)]
    assert ids == ["E0001", "E0002", "E0003"]

    incline = list_items(bank, query="incline")[0]
    assert incline["听写次数"] == 1 and incline["错误次数"] == 1
    assert incline["状态"] == "学习中" and incline["连续正确"] == 0
    deem = list_items(bank, query="deem")[0]
    assert deem["正确次数"] == 1 and deem["连续正确"] == 1


def test_duplicate_batch_is_rejected(bank):
    apply_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED)
    with pytest.raises(Exception) as ei:
        apply_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED)
    assert "已批改过" in str(ei.value)
    # 显式允许时才可以重跑
    res = apply_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED,
                        allow_duplicate=True)
    assert res["已写入"] is True


def test_key_item_rate(bank):
    res = preview_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED)
    assert res["重点题数"] == 1 and res["重点正确数"] == 1


def test_streak_two_clears_wrong_book(bank):
    # 第一次错 → 进错题本
    apply_grading(bank, "D20261116-01", DATE, "t.L1 p1", GRADED_MIXED)
    # 连续两次全对 → 状态升已掌握，错题本摘帽
    apply_grading(bank, "D20261116-02", DATE, "t.L1 p1", GRADED_ALL_RIGHT)
    apply_grading(bank, "D20261116-03", DATE, "t.L1 p1", GRADED_ALL_RIGHT)

    incline = list_items(bank, query="incline")[0]
    assert incline["连续正确"] == 2 and incline["状态"] == "已掌握"

    wb = load_workbook(bank)
    cleared = [r for r in range(2, wb[SHEET_WRONG].max_row + 1)
               if wb[SHEET_WRONG].cell(r, 11).value == "已摘帽"]
    assert cleared                                  # 至少一条被摘帽
    assert bank_stats(bank)["已摘帽错题"] >= 1


def test_override_wins_over_judge(bank):
    graded = [dict(g) for g in GRADED_MIXED]
    graded[0]["override"] = {"得分": 1, "错误类型": "", "批注": "人工裁定：连笔视为正确"}
    res = preview_grading(bank, "D20261116-01", DATE, "x", graded)
    assert res["明细"][0]["得分"] == 1
    assert res["明细"][0]["批注"] == "人工裁定：连笔视为正确"


def test_unknown_item_id_rejected(bank):
    with pytest.raises(Exception):
        preview_grading(bank, "D20261116-01", DATE, "x",
                        [{"词条ID": "W9999", "我的答案": "x"}])
