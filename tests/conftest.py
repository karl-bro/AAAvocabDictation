# -*- coding: utf-8 -*-
"""测试夹具：临时词库 + 一组覆盖全部评分分支的样例词条。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vocab_dictation.bank import add_items, init_bank  # noqa: E402

DATE = "2026-11-16"

SAMPLE_ITEMS = [
    {"序号": 1, "类型": "主词", "英文": "incline", "词性": "v.",
     "中文释义": "(使)倾斜；(使)倾向于"},
    {"序号": 1, "类型": "词组", "英文": "incline to do sth.", "中文释义": "倾向于做某事"},
    {"序号": 2, "类型": "主词", "英文": "deem", "词性": "v.", "中文释义": "认为；相信"},
    {"序号": 3, "类型": "主词", "英文": "optional/selective course",
     "中文释义": "选修课", "标记": "重点词"},
    {"序号": 4, "类型": "主词", "英文": "hinder", "词性": "v.",
     "中文释义": "阻碍，妨碍", "等号链": "是"},
    {"序号": 4, "类型": "主词", "英文": "hamper", "词性": "v.",
     "中文释义": "阻碍，妨碍", "等号链": "是"},
    {"序号": 5, "类型": "词组", "英文": "lay off", "中文释义": "解雇", "等号链": "是"},
]


@pytest.fixture()
def bank(tmp_path):
    """已初始化并写入 7 条样例词条的临时词库。"""
    path = str(tmp_path / "生词词库.xlsx")
    init_bank(path)
    add_items(path, SAMPLE_ITEMS, "t.L1-p1", DATE)
    return path


@pytest.fixture()
def empty_bank(tmp_path):
    path = str(tmp_path / "empty.xlsx")
    init_bank(path)
    return path


@pytest.fixture()
def graded_all_correct(bank):
    """全对答案数组，词条ID 从 W0001 起。"""
    return [{"词条ID": f"W{i:04d}", "我的答案": ans} for i, ans in enumerate(
        ["incline", "incline to do sth", "deem", "optional course",
         "hinder", "hamper", "lay off"], 1)]
