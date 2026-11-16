# -*- coding: utf-8 -*-
"""PDF 渲染层：听写卷（填空版 + 答案版）与批改报告。

reportlab 作为可选依赖（``pip install "vocab-dictation[pdf]"``），
未安装时本模块抛出带安装提示的 RuntimeError，不影响其余能力。
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Mapping, Sequence

FONT, FONT_B = "CN", "CN-B"
LEGEND = ('图例：★重点（红色波浪线）　◆熟僻（红圈标注的熟词僻义）　'
          '<font color="#7030A0">等号同义词链提示：默认给首字母；若同链成员前 n 个字母相同，'
          '则给到第 n+1 个字母（前缀）以便区分（仅此条件下提示）</font>')


def _require_reportlab():
    try:
        from reportlab.lib import colors  # noqa: F401
        from reportlab.platypus import Paragraph, SimpleDocTemplate  # noqa: F401
    except ImportError as e:  # pragma: no cover - 依赖缺失路径
        raise RuntimeError(
            "缺少 reportlab：pip install \"vocab-dictation[pdf]\"") from e


def _register_fonts() -> None:
    """按平台顺序找一款中文字体；全都没有才退回 reportlab 的 CJK CID 字体。

    CID 字体能显示中文，但部分 PDF 工具抽不出文本，会让自检失真，所以只作最后手段。
    """
    global FONT, FONT_B
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        # Windows
        (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"),
        (r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simhei.ttf"),
        (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\simsun.ttc"),
        # macOS
        ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc"),
        ("/System/Library/Fonts/Supplemental/Songti.ttc",
         "/System/Library/Fonts/Supplemental/Songti.ttc"),
        # Linux（Noto / 思源 / 文泉驿）
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
         "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
         "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
         "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for reg, bold in candidates:
        if not (os.path.exists(reg) and os.path.exists(bold)):
            continue
        try:
            for name, path in ((FONT, reg), (FONT_B, bold)):
                if path.lower().endswith(".ttc"):
                    pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
                else:
                    pdfmetrics.registerFont(TTFont(name, path))
            return
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    FONT = FONT_B = "STSong-Light"


def alpha_letters(s: str) -> list[str]:
    """只保留英文字母并小写。"""
    return [ch.lower() for ch in str(s) if ch.isalpha()]


def chain_prefix_length(items: Sequence[Mapping[str, Any]],
                        bank_path: str | None = None) -> dict[str, int]:
    """计算每条等号链（按中文释义分组）的最长公共前缀字母数 L。

    返回 ``{中文释义: L}``：同链成员前 L 个字母相同，第 L+1 个起才不同，
    因此提示到第 L+1 个字母即可区分。给出 ``bank_path`` 时以词库全链成员为准。
    """
    rows: list[tuple[Any, Any]] = []
    if bank_path:
        from openpyxl import load_workbook
        from .bank import BANK_COLS, SHEET_BANK, read_sheet
        wb = load_workbook(bank_path)
        rows = [(r["中文释义"], r["英文"]) for r in read_sheet(wb[SHEET_BANK], BANK_COLS)
                if r["等号链"] == "是"]
    else:
        rows = [(it["中文释义"], it["英文"]) for it in items if it.get("等号链") == "是"]

    groups: dict[str, list[list[str]]] = {}
    for cn, en in rows:
        groups.setdefault(str(cn), []).append(alpha_letters(en))

    out: dict[str, int] = {}
    for cn, ls in groups.items():
        if len(ls) < 2:
            out[cn] = 0
            continue
        L = 0
        while all(L < len(x) for x in ls) and len({x[L] for x in ls}) == 1:
            L += 1
        out[cn] = L
    return out


def _mark_tag(mark: str | None) -> str:
    return {"熟词僻义": '<font color="#C00000">◆熟僻</font>',
            "重点词": '<font color="#BF6F00">★重点</font>'}.get(mark or "", "")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s))


def _make_styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    return {
        "title": ParagraphStyle("t", fontName=FONT_B, fontSize=16, leading=22,
                                textColor=colors.HexColor("#1F4E79"), spaceAfter=2),
        "meta": ParagraphStyle("m", fontName=FONT, fontSize=9.5, leading=14,
                               textColor=colors.HexColor("#5A6B7E")),
        "cell": ParagraphStyle("c", fontName=FONT, fontSize=10.5, leading=14),
        "hint": ParagraphStyle("h", fontName=FONT_B, fontSize=10, leading=13,
                               alignment=1, textColor=colors.HexColor("#1F4E79")),
        "ans": ParagraphStyle("a", fontName=FONT_B, fontSize=11, leading=14,
                              textColor=colors.HexColor("#1F4E79")),
        "head": ParagraphStyle("hd", fontName=FONT_B, fontSize=10.5, leading=13,
                               alignment=1, textColor=colors.white),
        "body": ParagraphStyle("b", fontName=FONT, fontSize=9.5, leading=12.5),
        "body_b": ParagraphStyle("bb", fontName=FONT_B, fontSize=9.5, leading=12.5),
        "head_s": ParagraphStyle("hs", fontName=FONT_B, fontSize=9.5, leading=12,
                                 alignment=1, textColor=colors.white),
    }


def _esc(text: Any) -> str:
    """把纯文本转成 ReportLab 段落里安全的文本（只转义，不加标记）。"""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _paragraph(text: Any, style) -> Any:
    """纯文本段落：内容一律转义，避免用户数据里的 < & 破坏版式。"""
    from reportlab.platypus import Paragraph
    return Paragraph(_esc(text), style)


def _rich(markup: str, style) -> Any:
    """富文本段落：调用方自己保证标记正确，仅用于本文件内的固定版式片段。"""
    from reportlab.platypus import Paragraph
    return Paragraph(markup, style)


# ---------------- 听写卷 ----------------

def build_dictation_pdfs(items: Sequence[Mapping[str, Any]], meta: Mapping[str, Any],
                         outdir: str, prefix: str | None = None,
                         bank_path: str | None = None) -> dict[str, Any]:
    """一次产出一套听写卷：``<prefix>_填空版.pdf`` 与 ``<prefix>_答案版.pdf``。

    :param meta: ``{批次ID, 日期, 范围, 题量?, 说明?}``
    :param prefix: 文件名前缀，默认 ``听写_<日期>``
    :return: ``{"cloze": path, "answer": path, "pages": n, "verify": "OK"}``
    """
    _require_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

    _register_fonts()
    st = _make_styles()
    os.makedirs(outdir, exist_ok=True)
    prefix = prefix or f"听写_{meta['日期']}"
    prefix_L = chain_prefix_length(items, bank_path)

    def table(answer: bool):
        data = [[_paragraph(x, st["head"]) for x in
                 ("题号", "提示", "中文释义", "英文（单词 / 词组）")]]
        for i, it in enumerate(items, 1):
            hint = "词组" if it["类型"] == "词组" else (it.get("词性") or "")
            bits = [f'<font size="10">{_esc(hint)}</font>']
            tag = _mark_tag(it.get("标记"))
            if tag:
                bits.append(f'<font size="8.5">{tag}</font>')
            if it.get("等号链") == "是":
                letters = alpha_letters(it["英文"])
                L = prefix_L.get(str(it["中文释义"]), 0)
                show = "".join(letters[:L + 1])
                label = f"首字母 {show}" if L == 0 else f"前缀 {show}"
                bits.append(f'<font size="8.5" color="#7030A0">{_esc(label)}</font>')
            blank = (_paragraph(it["英文"], st["ans"]) if answer
                     else _rich("&nbsp;", st["cell"]))
            data.append([_paragraph(str(i), st["cell"]),
                         _rich("<br/>".join(bits), st["hint"]),
                         _paragraph(it["中文释义"], st["cell"]), blank])

        w = A4[0] - 22 * mm
        col_w = [11 * mm, 22 * mm, 62 * mm, w - 95 * mm]
        t = Table(data, colWidths=col_w, repeatRows=1)
        ts = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C7D9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("TOPPADDING", (0, 1), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]
        for r in range(1, len(data)):
            ts.append(("LINEBELOW", (3, r), (3, r), 1.0, colors.HexColor("#5A6B7E")))
            ts.append(("ROWBACKGROUNDS", (0, r), (-1, r),
                       [colors.white, colors.HexColor("#F6F9FC")]))
        t.setStyle(TableStyle(ts))
        return t

    out = {}
    for answer in (False, True):
        kind = "答案版" if answer else "填空版"
        path = os.path.join(outdir, f"{prefix}_{kind}.pdf")
        doc = SimpleDocTemplate(path, pagesize=A4,
                                leftMargin=11 * mm, rightMargin=11 * mm,
                                topMargin=12 * mm, bottomMargin=12 * mm,
                                title=f"生词听写 {kind}")
        story = [
            _paragraph(f"考研生词听写 · {kind}", st["title"]),
            _paragraph(f"批次：{meta['批次ID']}　日期：{meta['日期']}　"
                       f"范围：{meta.get('范围', '全部')}　题量：{len(items)}", st["meta"]),
            Spacer(1, 2 * mm),
            _paragraph(meta.get("说明",
                                "听写要求：根据中文释义写出对应英文（单词或词组），"
                                "注意词性提示；书写工整，词组写全。"), st["meta"]),
            Spacer(1, 3 * mm),
            table(answer),
            Spacer(1, 3 * mm),
            _rich(LEGEND, st["meta"]),
        ]
        doc.build(story)
        out["answer" if answer else "cloze"] = path

    out.update(verify_dictation_pdfs(items, meta, out["cloze"], out["answer"]))
    return out


def verify_dictation_pdfs(items: Sequence[Mapping[str, Any]], meta: Mapping[str, Any],
                          cloze: str, answer: str) -> dict[str, Any]:
    """自检：可打开、题号连续、中文释义与答案齐全；失败抛 AssertionError。"""
    try:
        import pymupdf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("缺少 pymupdf：pip install \"vocab-dictation[pdf]\"") from e

    errors: list[str] = []
    n = len(items)
    expect = set(str(i) for i in range(1, n + 1))

    for kind, path, need_answer in (("填空版", cloze, False), ("答案版", answer, True)):
        try:
            doc = pymupdf.open(path)
        except Exception as e:
            errors.append(f"{kind} 无法打开: {e}")
            continue
        text = "\n".join(pg.get_text("text") for pg in doc)
        flat = _norm(text)
        if meta["批次ID"] not in flat:
            errors.append(f"{kind} 缺少批次号 {meta['批次ID']}")
        if _norm(meta["日期"]) not in flat:
            errors.append(f"{kind} 缺少日期 {meta['日期']}")
        nums = set(re.findall(r"(?<!\d)(\d{1,3})(?!\d)", text))
        missing = expect - nums
        if missing:
            errors.append(f"{kind} 题号缺失: {sorted(missing, key=int)[:10]}")
        if any(m in text for m in ("<font", "&nbsp;", "<br/>")):
            errors.append(f"{kind} 富文本标记未解析，卷面出现源码")
        for it in items:
            cn = _norm(it["中文释义"])
            if cn and cn not in flat:
                errors.append(f"{kind} 中文释义未出现: {it['中文释义']}")
        if need_answer:
            low = _norm(text.lower())
            for it in items:
                for part in str(it["英文"]).split("/"):
                    if _norm(part.lower()) not in low:
                        errors.append(f"{kind} 答案未出现: {part}")
        pages = doc.page_count
        doc.close()
    if errors:
        raise AssertionError("听写卷自检失败:\n - " + "\n - ".join(errors[:10]))
    return {"verify": "OK", "cloze": cloze, "answer": answer}


# ---------------- 批改报告 ----------------

def build_report_pdf(result: Mapping[str, Any], out_path: str) -> dict[str, Any]:
    """由 ``grading.apply_grading`` / ``preview_grading`` 的结果生成批改报告。"""
    _require_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

    _register_fonts()
    st = _make_styles()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    rate = result["正确率"]
    key_rate = (result["重点正确数"] / result["重点题数"]) if result["重点题数"] else None
    detail = result["明细"]

    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=10 * mm,
                            rightMargin=10 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title="生词听写批改报告")
    story = [_paragraph("考研生词听写 · 批改报告", st["title"]), Spacer(1, 2 * mm),
             _paragraph(f"批次：{result['批次ID']}　日期：{result['日期']}　"
                        f"范围：{result['范围']}", st["meta"]), Spacer(1, 3 * mm)]

    overview = [
        [_paragraph(x, st["head_s"]) for x in ("得分", "正确率", "错题数", "重点/熟僻正确率")],
        [_paragraph(f"{result['得分']} / {result['满分']:g}", st["body_b"]),
         _paragraph(f"{rate * 100:.1f}%", st["body_b"]),
         _paragraph(str(result["错题数"]), st["body_b"]),
         _paragraph("未涉及" if key_rate is None else
                    f"{key_rate * 100:.1f}%（{result['重点正确数']}/{result['重点题数']}）",
                    st["body_b"])],
    ]
    t = Table(overview, colWidths=[(A4[0] - 20 * mm) / 4] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C7D9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [t, Spacer(1, 4 * mm)]

    if result["错因统计"]:
        rows = [[_paragraph("错因类型", st["head_s"]), _paragraph("数量", st["head_s"])]]
        for k, v in sorted(result["错因统计"].items(), key=lambda x: -x[1]):
            rows.append([_paragraph(k, st["body"]), _paragraph(str(v), st["body"])])
        t = Table(rows, colWidths=[60 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C7D9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [t, Spacer(1, 4 * mm)]

    rows = [[_paragraph(x, st["head_s"]) for x in
             ("题号", "中文释义", "你的答案", "正确答案", "得分", "批注")]]
    row_styles = []
    for d in detail:
        rows.append([_paragraph(d["题号"], st["body"]),
                     _paragraph(d["中文释义"], st["body"]),
                     _paragraph(d["我的答案"], st["body"]),
                     _paragraph(d["英文"], st["body"]),
                     _paragraph(f"{d['得分']:g}", st["body"]),
                     _paragraph(d["批注"], st["body"])])
        rr = len(rows) - 1
        bg = ("#EAF5EA" if d["得分"] == 1 else
              "#FFF6E5" if d["得分"] == 0.5 else "#FDECEC")
        row_styles.append(("BACKGROUND", (0, rr), (-1, rr), colors.HexColor(bg)))

    w = A4[0] - 20 * mm
    t = Table(rows, colWidths=[10 * mm, 42 * mm, 38 * mm, 38 * mm, 11 * mm,
                               w - 139 * mm], repeatRows=1)
    ts = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
          ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C7D9")),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3)] + row_styles
    t.setStyle(TableStyle(ts))
    story += [t, Spacer(1, 4 * mm)]

    wrong = [d for d in detail if d["得分"] < 1]
    tips: list[str] = []
    if wrong:
        tips.append("以下词条请立即抄默三遍；日后从词库抽查时将优先覆盖："
                    + "、".join(f"{d['英文']}（{d['中文释义']}）" for d in wrong[:12])
                    + ("……" if len(wrong) > 12 else ""))
    if any(d["错误类型"] == "拼写错误" for d in wrong):
        tips.append("拼写失误集中，建议按音节/词根拆分记忆，写完逐字母回读一遍再交。")
    if any("词组" in (d["错误类型"] or "") for d in wrong):
        tips.append("词组注意写全介词/冠词，固定搭配整体记忆。")
    if key_rate is not None and key_rate < 0.7:
        tips.append("重点词与熟词僻义正确率偏低，需回看原标注，把僻义放进例句中记。")
    if not tips:
        tips.append("全部正确，保持节奏；可适当加大明天抽查数量。")
    for idx, s in enumerate(tips, 1):
        story += [_paragraph(f"{idx}. {s}", st["body"]), Spacer(1, 1.5 * mm)]

    doc.build(story)
    verify_report(result, out_path)
    return {"path": out_path, "verify": "OK"}


def verify_report(result: Mapping[str, Any], out_path: str) -> None:
    """报告自检：题号连续、得分/正确率、正确答案与批注齐全。"""
    try:
        import pymupdf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("缺少 pymupdf：pip install \"vocab-dictation[pdf]\"") from e

    try:
        doc = pymupdf.open(out_path)
    except Exception as e:
        raise AssertionError(f"报告无法打开: {e}") from e

    text = "\n".join(pg.get_text("text") for pg in doc)
    flat, low = _norm(text), _norm(text.lower())
    errors: list[str] = []
    expect = set(str(i) for i in range(1, len(result["明细"]) + 1))
    missing = expect - set(re.findall(r"(?<!\d)(\d{1,3})(?!\d)", text))
    if missing:
        errors.append(f"题号缺失: {sorted(missing, key=int)[:10]}")
    if _norm(f"{result['得分']}/{result['满分']:g}") not in flat:
        errors.append("缺少得分")
    if _norm(f"{result['正确率'] * 100:.1f}%") not in flat:
        errors.append("缺少正确率")
    for d in result["明细"]:
        for part in str(d["英文"]).split("/"):
            if _norm(part.lower()) not in low:
                errors.append(f"正确答案未出现: {part}")
        if d["得分"] < 1:
            tag = _norm(d["批注"])[:8]
            if tag and tag not in flat:
                errors.append(f"第{d['题号']}题批注未出现: {d['批注']}")
    pages = doc.page_count
    doc.close()
    if errors:
        raise AssertionError("报告自检失败:\n - " + "\n - ".join(errors[:10]))
    if pages < 1:
        raise AssertionError("报告页数为 0")
