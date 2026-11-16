# -*- coding: utf-8 -*-
"""完成稿图片预处理（可选能力，需 ``pip install "vocab-dictation[image]"``）。

自动：小角度纠偏 → 检测多页拼接并分页 → 灰度/对比度增强 → 输出整页 PNG。
"""
from __future__ import annotations

import json
import os
from typing import Any, Sequence

DARK = 110            # 深色像素阈值
BAND_MIN_RATIO = 0.45
BAND_MIN_H = 4        # 粗黑分隔带最小厚度(px)
GAP_MIN_H = 35        # 宽空白带最小厚度(px)
MIN_WIDTH = 1400      # 低于此宽度给出重拍建议


def _require_imaging():
    try:
        import numpy as np
        from PIL import Image, ImageEnhance, ImageOps  # noqa: F401
        return np
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "缺少 Pillow/numpy：pip install \"vocab-dictation[image]\"") from e


def _to_gray_arr(im, np, width: int = 900):
    from PIL import ImageOps
    g = ImageOps.grayscale(im)
    scale = width / g.width
    if scale < 1:
        g = g.resize((width, max(1, int(g.height * scale))))
    return np.asarray(g, dtype=np.uint8)


def detect_split(im):
    """检测多页拼接的分隔位置，返回 ``(y, 依据)`` 或 ``None``。"""
    np = _require_imaging()
    g = _to_gray_arr(im, np, width=min(im.width, 1000))
    h, _ = g.shape
    dark = (g < DARK).mean(axis=1)

    # 1) 粗黑分隔带
    cand, run = [], None
    for y, v in enumerate(dark):
        if v > BAND_MIN_RATIO:
            run = run if run is not None else y
        else:
            if run is not None and y - run >= BAND_MIN_H and dark[run:y].mean() > 0.5:
                cand.append((run + y) // 2)
            run = None
    if run is not None and h - run >= BAND_MIN_H and dark[run:].mean() > 0.5:
        cand.append((run + h) // 2)
    cand = [c for c in cand if 0.08 * h < c < 0.92 * h]
    if cand:
        ys = cand[len(cand) // 2] if len(cand) > 1 else cand[0]
        return int(ys * im.height / h), "粗黑分隔带"

    # 2) 宽空白带
    blank, run, gaps = dark < 0.012, None, []
    for y, v in enumerate(blank):
        if v:
            run = run if run is not None else y
        else:
            if run is not None and y - run >= GAP_MIN_H:
                gaps.append((run + y) // 2)
            run = None
    if run is not None and h - run >= GAP_MIN_H:
        gaps.append((run + h) // 2)
    gaps = [c for c in gaps if 0.15 * h < c < 0.85 * h]
    if gaps:
        return int(min(gaps, key=lambda c: abs(c - h / 2)) * im.height / h), "宽空白带"
    return None


def deskew_angle(im) -> float:
    """基于水平投影方差估计倾斜角（±4°），表格横线场景有效。"""
    np = _require_imaging()
    from PIL import Image
    g = _to_gray_arr(im, np, width=760)
    binm = (g < 140).astype(np.uint8) * 255
    base = Image.fromarray(255 - binm)
    best_a, best_s = 0.0, -1.0
    for a in np.arange(-4.0, 4.01, 0.25):
        r = base.rotate(a, expand=False, fillcolor=255)
        proj = (255 - np.asarray(r)).sum(axis=1)
        s = proj.var()
        if s > best_s:
            best_s, best_a = s, float(a)
    return best_a if abs(best_a) >= 0.5 else 0.0


def enhance(im):
    from PIL import ImageEnhance, ImageOps
    g = ImageOps.grayscale(im)
    g = ImageOps.autocontrast(g, cutoff=1)
    return ImageEnhance.Sharpness(g).enhance(1.5)


def process_one(path: str, outdir: str, idx0: int = 1) -> tuple[list[dict], str, int]:
    _require_imaging()
    from PIL import Image
    im = Image.open(path).convert("RGB")
    split, how = detect_split(im), None
    if split:
        y, how = split
        pages = [im.crop((0, 0, im.width, y)), im.crop((0, y, im.width, im.height))]
    else:
        pages = [im]

    info = []
    for k, pg in enumerate(pages):
        angle = deskew_angle(pg)
        if angle:
            pg = pg.rotate(angle, expand=False, fillcolor=(255, 255, 255))
        pg = enhance(pg)
        if max(pg.size) > 4000:
            s = 4000 / max(pg.size)
            pg = pg.resize((int(pg.width * s), int(pg.height * s)), Image.LANCZOS)
        name = f"submission_page_{idx0 + k}.png"
        pg.save(os.path.join(outdir, name))
        warn = "" if pg.width >= MIN_WIDTH else "分辨率偏低，手写可能识别不清，建议重拍"
        info.append({"文件": name, "宽": pg.width, "高": pg.height,
                     "纠偏角度": angle, "警告": warn})
    return info, how, len(pages)


def prepare_submission(images: Sequence[str], outdir: str) -> dict[str, Any]:
    """批量预处理完成稿照片，返回分页清单与警告。"""
    _require_imaging()
    os.makedirs(outdir, exist_ok=True)
    all_info, idx = [], 1
    for p in images:
        info, how, n = process_one(p, outdir, idx)
        for d in info:
            d["来源"] = os.path.basename(p)
            d["分页依据"] = how or ""
        all_info += info
        idx += n
    summary = {"页数": len(all_info), "页面": all_info,
               "警告": [d["警告"] for d in all_info if d["警告"]]}
    with open(os.path.join(outdir, "prepare_info.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    return summary
