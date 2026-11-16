# -*- coding: utf-8 -*-
"""评分规则回归测试：锁定 1 / 0.5 / 0 的边界，防止口径漂移。"""
import pytest

from vocab_dictation.core import (ERR_BLANK, ERR_NONE, ERR_PHRASE_MISSING,
                                  ERR_PHRASE_ORDER, ERR_PHRASE_OTHER, ERR_SPELLING,
                                  ERR_UNKNOWN, compact, expand_slash, judge,
                                  levenshtein, norm_text)

ITEM_WORD = {"英文": "incline", "类型": "主词", "中文释义": "(使)倾斜"}
ITEM_PHRASE = {"英文": "incline to do sth.", "类型": "词组", "中文释义": "倾向于做某事"}
ITEM_SHORT = {"英文": "deem", "类型": "主词", "中文释义": "认为"}
ITEM_SLASH = {"英文": "optional/selective course", "类型": "主词", "中文释义": "选修课"}
ITEM_SPACE = {"英文": "lay off", "类型": "词组", "中文释义": "解雇"}


def test_text_helpers():
    assert norm_text("Self-Deception!") == "self deception"
    assert compact(" Pink  Slip ") == "pinkslip"
    assert levenshtein("incline", "indine") == 2
    assert expand_slash("optional/selective course") == ["optional course",
                                                         "selective course"]
    assert expand_slash("maintain/hold/believe that") == ["maintain that",
                                                          "hold that", "believe that"]


@pytest.mark.parametrize("answer", ["incline", "Incline", " incline ", "INCLINE!"])
def test_full_mark_normalization(answer):
    assert judge(answer, ITEM_WORD)[0] == 1


def test_full_mark_with_hyphen_and_punct():
    assert judge("self-deception", {"英文": "self--deception", "类型": "主词"})[0] == 1


def test_slash_any_branch_is_correct():
    score, etype, _ = judge("selective course", ITEM_SLASH)
    assert (score, etype) == (1, ERR_NONE)
    assert judge("optional course", ITEM_SLASH)[0] == 1


def test_half_mark_two_letters_off():
    score, etype, note = judge("indine", ITEM_WORD)
    assert score == 0.5 and etype == ERR_SPELLING
    assert "差 2 个字母" in note


def test_half_mark_short_word_one_letter_off():
    score, etype, _ = judge("deam", ITEM_SHORT)
    assert score == 0.5 and etype == ERR_SPELLING


def test_short_word_three_letters_distant():
    # 短词只容错 1 个字母；偏差更大时按“完全不会”处理（不会误给 0.5）
    score, etype, _ = judge("dxx", ITEM_SHORT)
    assert score == 0 and etype == ERR_UNKNOWN


def test_phrase_missing_word_is_zero():
    score, etype, note = judge("indine to do sth", ITEM_PHRASE)
    assert score == 0 and etype == ERR_PHRASE_MISSING
    assert "incline" in note


def test_phrase_extra_word_is_zero():
    score, etype, _ = judge("a pink slip", {"英文": "pink slip", "类型": "词组"})
    assert score == 0 and etype == ERR_PHRASE_OTHER


def test_phrase_wrong_order_is_zero():
    score, etype, _ = judge("off lay", ITEM_SPACE)
    assert score == 0 and etype == ERR_PHRASE_ORDER


def test_phrase_exact_with_trailing_period():
    assert judge("lay off.", ITEM_SPACE)[0] == 1


@pytest.mark.parametrize("answer", ["", None, "   ", "..."])
def test_blank_is_zero(answer):
    score, etype, _ = judge(answer, ITEM_WORD)
    assert score == 0 and etype == ERR_BLANK


def test_unrelated_word_is_unknown():
    score, etype, _ = judge("entail", ITEM_SHORT)
    assert score == 0 and etype == ERR_UNKNOWN


def test_phrase_judged_by_phrase_branch_even_if_type_is_main():
    # 多词答案自动走词组分支，避免把“词组漏词”误判成拼写错误
    item = {"英文": "pink slip", "类型": "主词"}
    assert judge("pink", item)[1] == ERR_PHRASE_MISSING
