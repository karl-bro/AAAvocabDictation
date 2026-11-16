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


def test_build_report_pdf(bank, tmp_path):
    res = preview_grading(bank, "D20261116-01", "2026-11-16", "t.L1 p1", [
        {"词条ID": "W0001", "我的答案": "indine"},
        {"词条ID": "W0003", "我的答案": "deem"},
    ])
    out = str(tmp_path / "report.pdf")
    info = build_report_pdf(res, out)
    assert info["verify"] == "OK" and os.path.getsize(out) > 1000
