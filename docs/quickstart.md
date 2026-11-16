# 快速开始（5 分钟）

## 1. 安装

```bash
git clone https://github.com/karl-bro/AAAvocabDictation.git
cd vocab-dictation
python -m venv .venv
# Windows: .venv\Scripts\activate ；macOS/Linux: source .venv/bin/activate
pip install -e ".[pdf]"        # 只做词库/判分逻辑可用 pip install -e .
```

只想看效果、不装包：在仓库根目录设 `PYTHONPATH=src` 后直接跑示例。

## 2. 跑通一条龙

```bash
python examples/01_quickstart.py
```

预期输出（路径因系统而异）：

```
入库 19 条，跳过 0 条重复
词库统计： {"词条总数": 19, "按状态": {"未听写": 19}, ...}
试卷： …\听写_demo_填空版.pdf
答案： …\听写_demo_答案版.pdf
自检： OK
预判：18.5/19.0 分，错 1 题
报告： …\批改报告_demo.pdf 自检： OK
```

示例全部在系统临时目录建库，不会碰到你的真实词库。

## 3. 三种最常用调用

### 直接调函数

```python
from vocab_dictation import VocabDictation

vd = VocabDictation("E:/vocab/生词词库.xlsx")
vd.init()                                    # 首次建库（已存在会报 BANK_EXISTS）
vd.add_items(items, source="v.L5-p1", date="2026-11-16")
items = vd.shuffle_all(seed=2026)            # 全量打乱，不补题
batch = vd.next_batch_id("2026-11-16")
vd.build_dictation_pdf(items, {"批次ID": batch, "日期": "2026-11-16"})
```

### 命令行

```bash
vocabdict capabilities --pretty
vocabdict call --action dictation.sample --bank 生词词库.xlsx --params "{\"n\": 20}" --pretty
```

### 起服务给别的应用调

```bash
vocabdict serve --port 8800 --bank 生词词库.xlsx --token my-secret
```

```bash
curl -s http://127.0.0.1:8800/call \
  -H "Authorization: Bearer my-secret" \
  -H "Content-Type: application/json" \
  -d '{"action":"bank.stats"}'
```

## 4. 第二次以后

- 词库路径固定后，用环境变量省掉每次传参：`set VOCAB_DICTATION_BANK=E:\vocab\生词词库.xlsx`（Windows）/ `export ...`（macOS/Linux）。
- 每天同一批次号只能 `grading.apply` 一次；要重批用 `allow_duplicate: true`。
- 想复现某天的卷子顺序：把当天的 `seed` 记下来，`shuffle_all`/`sample` 传同一个 `seed`。

## 5. 下一步

| 想知道 | 看 |
| --- | --- |
| 每个动作的参数与返回值 | [api-reference.md](api-reference.md) |
| 评分为什么给 0.5 而不是 0 | [scoring-rules.md](scoring-rules.md) |
| 怎么接进 OpenAI / Claude / 自己的 App | [integration.md](integration.md) |
| 怎么让模型自己识别生词本照片 | `prompts/extract_items.md` |
