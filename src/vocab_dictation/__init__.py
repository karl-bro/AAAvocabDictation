# -*- coding: utf-8 -*-
"""vocab-dictation —— 考研生词听写闭环的可复用工具箱。

两种用法：

1. 一行调用（任何动作都能走同一个口子）::

       from vocab_dictation import dispatch
       r = dispatch("bank.stats", {"bank": "词库.xlsx"})

2. 面向对象（推荐给业务代码）::

       from vocab_dictation import VocabDictation
       vd = VocabDictation("词库.xlsx")
       vd.shuffle_all(seed=42)
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .api import (ACTION_SPECS, BANK_ENV, VERSION, ToolError, capabilities,
                  call_json, dispatch)
from .core import (ERROR_TYPES, ERR_BLANK, ERR_NONE, ERR_PHRASE_MISSING,
                   ERR_PHRASE_ORDER, ERR_PHRASE_OTHER, ERR_SPELLING, ERR_UNKNOWN,
                   compact, expand_slash, judge, levenshtein, norm_text)
from .bank import (BANK_COLS, LOG_COLS, WRONG_COLS, BankError, BankExists,
                   BankNotFound, DuplicateBatch)

__all__ = [
    "dispatch", "call_json", "capabilities", "VocabDictation", "VERSION",
    "ToolError", "judge", "expand_slash", "levenshtein", "norm_text", "compact",
    "ERROR_TYPES", "BANK_COLS", "WRONG_COLS", "LOG_COLS",
    "BankError", "BankExists", "BankNotFound", "DuplicateBatch",
]
__version__ = VERSION


class VocabDictation:
    """把统一接口包成对象，固定词库路径，便于在应用里复用。

    所有方法都返回 ``dispatch`` 解包后的 ``data``；失败抛 :class:`ToolError`。
    """

    def __init__(self, bank: str, workdir: str | None = None):
        self.bank = bank
        self.workdir = workdir

    # -- 内部 --
    def _call(self, action: str, **params: Any) -> Any:
        res = dispatch(action, params, bank=self.bank)
        if not res["ok"]:
            err = res["error"]
            raise ToolError(err["code"], err["message"], err["details"])
        return res["data"]

    def _unwrap(self, action: str, **params: Any) -> dict[str, Any]:
        data = self._call(action, **params)
        return data

    # -- 词库 --
    def init(self, overwrite: bool = False) -> str:
        return self._unwrap("bank.init", path=self.bank, overwrite=overwrite)["path"]

    def add_items(self, items: Sequence[Mapping[str, Any]], source: str,
                  date: str | None = None) -> dict[str, Any]:
        return self._unwrap("bank.add_items", items=list(items), source=source, date=date)

    def list_items(self, **filters: Any) -> list[dict[str, Any]]:
        return self._unwrap("bank.list_items", **filters)["items"]

    def update_item(self, item_id: str, **fields: Any) -> dict[str, Any]:
        return self._unwrap("bank.update_item", item_id=item_id, fields=fields)

    def stats(self) -> dict[str, Any]:
        return self._unwrap("bank.stats")

    # -- 出卷 --
    def next_batch_id(self, date: str | None = None) -> str:
        return self._unwrap("dictation.batch_id", date=date)["batch_id"]

    def sample(self, n: int, scope: Mapping[str, Any] | None = None,
               seed: Any = None, wrong_ratio: float = 0.6) -> list[dict[str, Any]]:
        return self._unwrap("dictation.sample", n=n, scope=scope, seed=seed,
                            wrong_ratio=wrong_ratio)["items"]

    def shuffle_all(self, scope: Mapping[str, Any] | None = None,
                    seed: Any = None) -> list[dict[str, Any]]:
        return self._unwrap("dictation.shuffle_all", scope=scope, seed=seed)["items"]

    def build_dictation_pdf(self, items: Sequence[Mapping[str, Any]],
                            meta: Mapping[str, Any], outdir: str | None = None,
                            prefix: str | None = None) -> dict[str, Any]:
        outdir = outdir or self.workdir or "."
        return self._unwrap("dictation.build_pdf", items=list(items), meta=meta,
                            outdir=outdir, prefix=prefix)

    # -- 批改 --
    def preview(self, graded: Sequence[Mapping[str, Any]], batch_id: str,
                date: str | None = None, scope: str = "") -> dict[str, Any]:
        return self._unwrap("grading.preview", graded=list(graded), batch_id=batch_id,
                            date=date, scope=scope)

    def apply(self, graded: Sequence[Mapping[str, Any]], batch_id: str,
              date: str | None = None, scope: str = "", note: str = "",
              allow_duplicate: bool = False) -> dict[str, Any]:
        return self._unwrap("grading.apply", graded=list(graded), batch_id=batch_id,
                            date=date, scope=scope, note=note,
                            allow_duplicate=allow_duplicate)

    # -- 报告与图像 --
    def build_report(self, result: Mapping[str, Any], out: str) -> dict[str, Any]:
        return self._unwrap("report.build", result=dict(result), out=out)

    def prepare_submission(self, images: Sequence[str],
                           outdir: str | None = None) -> dict[str, Any]:
        return self._unwrap("submission.prepare", images=list(images),
                            outdir=outdir or self.workdir or ".")

    def capabilities(self) -> dict[str, Any]:
        return capabilities()
