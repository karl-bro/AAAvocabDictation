# -*- coding: utf-8 -*-
"""核心纯逻辑：文本归一化、编辑距离、评分引擎。

本模块不依赖任何 I/O，可独立导入与单元测试。
评分口径（与上游技能保持字节级一致，改动会导致历史分数漂移）：
  * 拼写完全正确（斜杠同义词任一命中）= 1 分
  * 单词错 1~2 个字母且整体可辨认 = 0.5 分（短词 3~4 字母只容错 1 个）
  * 偏差过大 / 未作答 / 词组漏词·多词·错序 = 0 分
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

# 错误类型枚举（写库与报表统计共用，勿随意增删）
ERR_NONE = ""
ERR_SPELLING = "拼写错误"
ERR_PHRASE_ORDER = "词序错误"
ERR_PHRASE_MISSING = "词组漏词"
ERR_PHRASE_OTHER = "词组错误"
ERR_BLANK = "未作答"
ERR_UNKNOWN = "完全不会"

ERROR_TYPES: Sequence[str] = (
    ERR_SPELLING, ERR_PHRASE_ORDER, ERR_PHRASE_MISSING,
    ERR_PHRASE_OTHER, ERR_BLANK, ERR_UNKNOWN,
)

# 需要单独统计正确率的标记
KEY_MARKS = ("熟词僻义", "重点词")

_PUNCT_RE = re.compile(r"[.,，。；;：:!！?？（）()\[\]【】\"'’‘…~～=]")


def norm_text(value: Any) -> str:
    """归一化：小写、去标点、连字符/斜杠转空格、压缩空白。"""
    s = str(value if value is not None else "").lower()
    s = _PUNCT_RE.sub(" ", s)
    s = s.replace("-", " ").replace("/", " ").replace("／", " ")
    return re.sub(r"\s+", " ", s).strip()


def compact(value: Any) -> str:
    """去空白后的归一化串，用于零空格比较。"""
    return norm_text(value).replace(" ", "")


def levenshtein(a: str, b: str) -> int:
    """编辑距离（插入/删除/替换均为 1）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def expand_slash(expected: str) -> list[str]:
    """展开斜杠同义词，正确处理斜杠只落在短语部分词上的情况。

    >>> expand_slash("optional/selective course")
    ['optional course', 'selective course']
    >>> expand_slash("maintain/hold/believe that")
    ['maintain that', 'hold that', 'believe that']
    """
    s = str(expected).replace("／", "/")
    combos = [""]
    for part in s.split():
        if "/" in part:
            opts = [o for o in part.split("/") if o]
            combos = [((c + " " + o).strip() if c else o) for c in combos for o in opts]
        else:
            combos = [(c + " " + part).strip() if c else part for c in combos]
    return combos


def judge(answer: Any, item: Mapping[str, Any]) -> tuple[float, str, str]:
    """对单个词条判分。

    :param answer: 学生作答原文（未作答传空串或 None）
    :param item: 词条字典，至少需要 ``英文`` 与 ``类型``
    :return: ``(得分, 错误类型, 批注)``
    """
    expected = str(item["英文"])
    alts = expand_slash(expected)

    if answer is None or compact(answer) == "":
        return 0.0, ERR_BLANK, "未填写，需重点背记"

    is_phrase = item.get("类型") == "词组" or any(
        len(norm_text(a).split()) > 1 for a in alts)

    if is_phrase:
        exp_tokens = [norm_text(a).split() for a in alts]
        got_tokens = norm_text(answer).split()
        if any(got_tokens == et for et in exp_tokens):
            return 1.0, ERR_NONE, "正确"
        for et in exp_tokens:
            if set(got_tokens) == set(et) and len(got_tokens) == len(et):
                return 0.0, ERR_PHRASE_ORDER, f"应为“{' '.join(et)}”"
        for et in exp_tokens:
            missing = [w for w in et if got_tokens.count(w) < et.count(w)]
            if missing:
                return 0.0, ERR_PHRASE_MISSING, f"漏了 {missing}；完整写法“{' '.join(et)}”"
        return 0.0, ERR_PHRASE_OTHER, f"应为“{expected}”"

    got = compact(answer)
    alts_compact = [compact(a) for a in alts]
    if got in alts_compact or got == "".join(alts_compact):
        return 1.0, ERR_NONE, "正确"
    got_tokens = set(norm_text(answer).split())
    if got_tokens and got_tokens == set(norm_text(expected).split()):
        return 1.0, ERR_NONE, "正确"

    for a in alts:
        exp = compact(a)
        d = levenshtein(got, exp)
        if d <= 2 and len(exp) >= 5:
            return 0.5, ERR_SPELLING, f"差 {d} 个字母，正确拼写“{a.strip()}”"
        if d == 1 and 3 <= len(exp) < 5:
            return 0.5, ERR_SPELLING, f"差 1 个字母，正确拼写“{a.strip()}”"
        ratio = 1 - d / max(len(exp), 1)
        if ratio >= 0.6:
            return 0.0, ERR_SPELLING, f"拼写偏差较大，应为“{expected}”"
    return 0.0, ERR_UNKNOWN, f"应为“{expected}”"


def is_key_item(item: Mapping[str, Any]) -> bool:
    """是否为重点词/熟词僻义（单独统计正确率）。"""
    return item.get("标记") in KEY_MARKS
