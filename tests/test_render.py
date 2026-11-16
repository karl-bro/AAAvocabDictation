# -*- coding: utf-8 -*-
"""渲染层测试：听写卷双版本与批改报告的自检链路。"""
import os

import pytest

pytest.importorskip("reportlab")
pytest.importorskip("pymupdf")

from vocab_dictation.bank import list_items  # noqa: E402
from vocab_dictation.grading import preview_grading  # noqa: E402
from vocab_dictation.rendering import (build_dictation_pdfs,  # noqa: E402
                                       build_report_pdf, chain_prefix_length)

META = {"批次ID": "D20261116-01", "日期": "2026-11-16", "范围": "t.L1 p1"}


def test_build_dictation_pdfs_self_check(bank, tmp_path):
    items = list_items(bank)
    paths = build_dictation_pdfs(items, META, str(tmp_path), prefix="听写_test",
                                 bank_path=bank)
    assert paths["verify"] == "OK"
    for key in ("cloze", "answer"):
        assert os.path.getsize(paths[key]) > 1000
    assert os.path.basename(paths["cloze"]) == "听写_test_填空版.pdf"
    assert os.path.basename(paths["answer"]) == "听写_test_答案版.pdf"


def test_cloze_has_no_answers(bank, tmp_path):
    import pymupdf
    items = list_items(bank)
    paths = build_dictation_pdfs(items, META, str(tmp_path), prefix="t2",
                                 bank_path=bank)
    doc = pymupdf.open(paths["cloze"])
    text = "\n".join(p.get_text() for p in doc)
    doc.close()
    # 填空版不应出现作为答案的英文单词（中文释义仍在）
    assert "incline to do sth" not in text
    assert "倾向于做某事" in text


def test_chain_prefix_length(bank):
    items = list_items(bank)
    prefix = chain_prefix_length(items)
    # hinder / hamper 前 1 个字母相同 → 需提示到第 2 个字母
    assert prefix["阻碍，妨碍"] == 1


def test_dictation_does_not_leak_markup(tmp_path):
    """卷面必须渲染成标签，而不是把 <font>/&nbsp; 当文字印出来。"""
    import re

    import pymupdf

    items = [
        {"序号": 1, "类型": "主词", "英文": "deem", "词性": "v.",
         "中文释义": "认为", "标记": "熟词僻义", "等号链": ""},
        {"序号": 2, "类型": "主词", "英文": "defy", "词性": "v.",
         "中文释义": "违抗", "标记": "重点词", "等号链": ""},
        {"序号": 3, "类型": "主词", "英文": "hinder", "词性": "v.",
         "中文释义": "阻碍，妨碍", "标记": "普通", "等号链": "是"},
        {"序号": 4, "类型": "主词", "英文": "hamper", "词性": "v.",
         "中文释义": "阻碍，妨碍", "标记": "普通", "等号链": "是"},
        {"序号": 5, "类型": "词组", "英文": "incline to do sth", "词性": "",
         "中文释义": "倾向于做某事", "标记": "普通", "等号链": ""},
    ]
    paths = build_dictation_pdfs(items, META, str(tmp_path), prefix="leak")
    text = "\n".join(p.get_text("text") for p in pymupdf.open(paths["cloze"]))

    assert "<font" not in text and "&nbsp;" not in text and "<br/>" not in text
    # 标记与提示都要真的出现在卷面上
    assert "熟僻" in text and "重点" in text
    assert re.search(r"前缀\s+ha", text)  # hinder/hamper 共同前缀 h，多给一个字母
    assert "词组" in text


def test_build_report_pdf(bank, tmp_path):
    res = preview_grading(bank, "D20261116-01", "2026-11-16", "t.L1 p1", [
        {"词条ID": "W0001", "我的答案": "indine"},
        {"词条ID": "W0003", "我的答案": "deem"},
    ])
    out = str(tmp_path / "report.pdf")
    info = build_report_pdf(res, out)
    assert info["verify"] == "OK" and os.path.getsize(out) > 1000
