# -*- coding: utf-8 -*-
"""词库层测试：初始化、去重入库、查询、就地改、抽样、批次号、统计。"""
import pytest
from openpyxl import load_workbook

from vocab_dictation.bank import (BANK_COLS, BankExists, BankNotFound, LOG_COLS,
                                  SHEET_BANK, SHEET_LOG, SHEET_WRONG, add_items,
                                  bank_stats, init_bank, list_items, next_batch_id,
                                  read_sheet, sample_items, shuffle_all, update_item)


def test_init_creates_four_sheets(tmp_path):
    path = str(tmp_path / "b.xlsx")
    init_bank(path)
    wb = load_workbook(path)
    assert wb.sheetnames == ["使用说明", SHEET_BANK, SHEET_WRONG, SHEET_LOG]
    assert [c.value for c in wb[SHEET_BANK][1]] == BANK_COLS


def test_init_refuses_to_overwrite(tmp_path):
    path = str(tmp_path / "b.xlsx")
    init_bank(path)
    with pytest.raises(BankExists):
        init_bank(path)
    init_bank(path, overwrite=True)  # 显式重建才允许


def test_missing_bank_raises(tmp_path):
    with pytest.raises(BankNotFound):
        list_items(str(tmp_path / "nope.xlsx"))


def test_add_items_dedupes_same_source_seq_word(bank):
    before = len(list_items(bank))
    again = add_items(bank, [
        {"序号": 1, "类型": "主词", "英文": "Incline", "中文释义": "x"},
        {"序号": 9, "类型": "词组", "英文": "in the end", "中文释义": "最后"},
    ], "t.L1-p1")
    assert len(again["added"]) == 1           # 大小写不同也算重复
    assert len(again["skipped"]) == 1
    assert len(list_items(bank)) == before + 1


def test_add_items_validates_type_and_mark(bank):
    with pytest.raises(Exception):
        add_items(bank, [{"序号": 10, "类型": "乱写", "英文": "x", "中文释义": "y"}], "s")
    with pytest.raises(Exception):
        add_items(bank, [{"序号": 11, "类型": "主词", "英文": "x", "中文释义": "y",
                          "标记": "紫词"}], "s")


def test_list_items_filters(bank):
    assert len(list_items(bank)) == 7
    assert len(list_items(bank, item_type="词组")) == 2
    assert [r["英文"] for r in list_items(bank, query="incline")] == [
        "incline", "incline to do sth."]
    assert list_items(bank, source="t.L1-p1", limit=3)[0]["词条ID"] == "W0001"


def test_update_item_in_place(bank):
    res = update_item(bank, "W0005", {"中文释义": "阻碍；妨碍", "等号链": "是"})
    assert res["changed"] == ["中文释义", "等号链"]
    row = list_items(bank, query="hinder")[0]
    assert row["中文释义"] == "阻碍；妨碍"
    assert row["听写次数"] == 0              # 统计列不被触碰


def test_update_item_rejects_unknown_field(bank):
    with pytest.raises(Exception):
        update_item(bank, "W0001", {"听写次数": 99})


def test_sample_returns_shuffled_subset(bank):
    items = sample_items(bank, 3, seed=7)
    assert len(items) == 3
    assert all(it["词条ID"] in {f"W{i:04d}" for i in range(1, 8)} for it in items)


def test_sample_is_reproducible_with_seed(bank):
    a = [i["词条ID"] for i in sample_items(bank, 5, seed=42)]
    b = [i["词条ID"] for i in sample_items(bank, 5, seed=42)]
    assert a == b


def test_sample_respects_scope(bank):
    items = sample_items(bank, 5, scope={"类型": ["词组"]}, seed=1)
    assert {i["类型"] for i in items} == {"词组"}


def test_shuffle_all_covers_everything(bank):
    items = shuffle_all(bank, seed=3)
    assert len(items) == 7
    assert {i["词条ID"] for i in items} == {f"W{i:04d}" for i in range(1, 8)}


def test_shuffle_all_scope_excludes(bank):
    items = shuffle_all(bank, scope={"序号区间": [1, 2]}, seed=3)
    assert {int(i["序号"]) for i in items} == {1, 2}


def test_batch_id_sequence(bank):
    assert next_batch_id(bank, "2026-11-16") == "D20261116-01"
    wb = load_workbook(bank)
    wb[SHEET_LOG].append(["D20261116-01", "2026-11-16", "x", 7, 7.0, 1.0, 0, 2, 2, ""])
    wb.save(bank)
    assert next_batch_id(bank, "2026-11-16") == "D20261116-02"


def test_bank_stats(bank):
    st = bank_stats(bank)
    assert st["词条总数"] == 7
    assert st["按状态"] == {"未听写": 7}
    assert st["按类型"] == {"主词": 5, "词组": 2}
    assert st["等号链成员"] == 3
    assert st["错题总数"] == 0
    assert st["听写批次数"] == 0


def test_read_sheet_marks_row_numbers(bank):
    wb = load_workbook(bank)
    rows = read_sheet(wb[SHEET_BANK], BANK_COLS)
    assert rows[0]["_row"] == 2 and rows[-1]["_row"] == 8
