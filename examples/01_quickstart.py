# -*- coding: utf-8 -*-
"""示例 1：一条龙跑完「入库 → 全量打乱出卷 → 批改 → 报告」。

直接运行（仓库根目录）：

    python examples/01_quickstart.py

会在系统临时目录建一个独立的演示词库，不碰任何真实数据。
"""
import json
import tempfile
from pathlib import Path

from _console import utf8_stdout
from vocab_dictation import VocabDictation, expand_slash

HERE = Path(__file__).resolve().parent
ITEMS = json.loads((HERE.parent / "assets" / "sample_items.json").read_text(encoding="utf-8"))
DATE = "2026-11-16"


def main() -> None:
    utf8_stdout()
    work = Path(tempfile.mkdtemp(prefix="vocab-demo-"))
    bank = work / "生词词库.xlsx"
    vd = VocabDictation(str(bank), workdir=str(work))

    vd.init()
    added = vd.add_items(ITEMS, source="demo-p1", date=DATE)
    print(f"入库 {len(added['added'])} 条，跳过 {len(added['skipped'])} 条重复")
    print("词库统计：", json.dumps(vd.stats(), ensure_ascii=False))

    # 全量打乱出卷（不从词库补题）
    items = vd.shuffle_all(seed=2026)
    batch = vd.next_batch_id(DATE)
    pdfs = vd.build_dictation_pdf(
        items,
        meta={"批次ID": batch, "日期": DATE, "范围": "demo-p1（全量打乱）",
              "说明": "按中文写英文，词组写全"},
        prefix="听写_demo",
    )
    print("试卷：", pdfs["cloze"])
    print("答案：", pdfs["answer"])
    print("自检：", pdfs["verify"])

    # 模拟交卷：第 1 题少打一个字母，其余照抄词条（斜杠项取第一支）
    graded = []
    for i, it in enumerate(items, 1):
        ans = expand_slash(it["英文"])[0]
        if i == 1:
            ans = ans[:-1]
        graded.append({"词条ID": it["词条ID"], "我的答案": ans})

    preview = vd.preview(graded, batch_id=batch, date=DATE, scope="demo-p1（全量打乱）")
    print(f"预判：{preview['得分']}/{preview['满分']} 分，错 {preview['错题数']} 题")

    result = vd.apply(graded, batch_id=batch, date=DATE, scope="demo-p1（全量打乱）")
    report = vd.build_report(result, str(work / "批改报告_demo.pdf"))
    print("报告：", report["path"], "自检：", report["verify"])
    print("产物目录：", work)


if __name__ == "__main__":
    main()
