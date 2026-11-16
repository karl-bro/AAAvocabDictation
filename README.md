# vocab-dictation

**A reusable, model-agnostic skill for the full vocabulary-dictation loop.**
Turn a photographed vocabulary notebook into a graded, tracked, print-ready dictation cycle —
with one JSON interface that any LLM app, agent framework, or backend can call.

[中文说明](README.zh-CN.md) · [Quickstart](docs/quickstart.md) · [API](docs/api-reference.md) · [Scoring rules](docs/scoring-rules.md) · [Integration](docs/integration.md)

---

## Why this exists

Preparing for a vocabulary exam by hand is a five-step loop that nobody wants to re-do every day:

1. read the day's handwritten notebook page,
2. type every word into a list,
3. pick words, shuffle, lay out a printable quiz,
4. grade the handwritten answers,
5. track what was wrong, and how often.

Most "AI vocabulary" tools do step 3 only. This project packages the **whole loop** as one
skill with a stable contract, so the LLM in your app only has to do what LLMs are good at
(read handwriting, follow the workflow) and everything else is deterministic, testable code.

## What it does

| Capability | Detail |
| --- | --- |
| Bank management | one `.xlsx` workbook, 4 sheets (guide / words / wrong book / session log), auto IDs, dedupe by `source+seq+word` |
| Quiz building | wrong-book-first sampling (`sample`) **or** full shuffle of everything in scope (`shuffle_all`), reproducible via `seed` |
| PDF output | cloze + answer versions, auto self-check (page count, contiguous question numbers, all text present) |
| Grading | 1 / 0.5 / 0 with fixed rules; slash synonyms accepted; phrase missing-word / extra-word / wrong-order detection |
| Tracking | per-word attempts, correct count, streak; half marks count as errors |
| Wrong-book lifecycle | auto clear after **two consecutive full marks**, streak resets on any miss |
| Report | PDF with per-question detail, error-type distribution, key-word accuracy, review suggestions |
| Letter hints | only for `=`-chain members (including the head word); if chain members share `n` leading letters, hint up to letter `n+1` |

Both `sample` (wrong-book priority) and `shuffle_all` (full, no back-fill) are first-class —
because "give me everything, shuffled" and "give me 20, hardest first" are different jobs.

## Architecture

```
                    ┌──────────────────────────────┐
  Python SDK ──────▶│                              │
  CLI ─────────────▶│   dispatch(action, params)   │──▶ core.py     (pure scoring, no I/O)
  HTTP  /call ─────▶│   single JSON envelope       │──▶ bank.py     (xlsx read/write)
  MCP  tools/call ──▶│                              │──▶ grading.py  (preview / apply)
                    └──────────────────────────────┘──▶ rendering.py(PDF + self-check)
                                                        prepare.py  (photo pre-processing)
```

- `core.py` has **zero I/O dependencies**: scoring rules are unit-testable without a workbook.
- `api.py` is the only place that knows every action; `ACTION_SPECS` is the single source of
  truth from which `capabilities()` derives JSON Schema for every protocol.
- Adapters (`cli.py`, `http_server.py`, `mcp_server.py`) are thin: they translate transport
  into `dispatch` and nothing else.

## Install

```bash
pip install "vocab-dictation[pdf]"     # openpyxl is required; pdf extra for quiz/report
# extras: [pdf] reportlab+pymupdf | [image] pillow+numpy | [dev] pytest + all
```

Python ≥ 3.9. No network, no API keys, no cloud service.

## Quickstart

```python
from vocab_dictation import VocabDictation

vd = VocabDictation("词库.xlsx")
vd.init()
vd.add_items(items, source="v.L5-p1", date="2026-11-16")

items = vd.shuffle_all(seed=2026)                 # everything, shuffled, no back-fill
meta = {"批次ID": vd.next_batch_id("2026-11-16"), "日期": "2026-11-16", "范围": "v.L5 p1"}
vd.build_dictation_pdf(items, meta, outdir="out") # → 填空版.pdf + 答案版.pdf (+ verify OK)

graded = [{"词条ID": it["词条ID"], "我的答案": ans} for it, ans in zip(items, answers)]
vd.apply(graded, batch_id=meta["批次ID"], date=meta["日期"])
vd.build_report(result, "out/批改报告.pdf")
```

Run the end-to-end demo (writes only into a temp dir):

```bash
python examples/01_quickstart.py
python examples/02_llm_tool_call.py   # OpenAI / Anthropic tool declarations
python examples/03_http_client.py     # POST /call round-trip
python examples/04_mcp_client.py      # MCP handshake over stdio
```

## Four entrypoints, one behaviour

```bash
vocabdict capabilities --pretty                          # what can it do
vocabdict call --action bank.stats --bank 词库.xlsx       # one-shot call
vocabdict serve --port 8800 --bank 词库.xlsx --token T    # HTTP JSON service
vocabdict mcp                                            # MCP stdio server
```

```bash
curl -s localhost:8800/call -H "Authorization: Bearer T" \
  -H 'Content-Type: application/json' \
  -d '{"action":"dictation.shuffle_all","params":{"seed":7}}'
```

All four return the same envelope, so an app can switch transports without touching business code.

## The contract

Request:

```json
{"action": "dictation.sample", "params": {"n": 20, "seed": 7}, "bank": "词库.xlsx"}
```

Response (success and failure are structurally identical, only `ok`/`error` differ):

```json
{
  "ok": true,
  "action": "dictation.sample",
  "version": "1.0.0",
  "data": {"count": 20, "items": ["..."]},
  "warnings": [],
  "error": null,
  "meta": {"elapsed_ms": 12, "bank": "E:/vocab/词库.xlsx"}
}
```

Error codes are meant to be **branchable**, not just printed:

`INVALID_ACTION` · `INVALID_PARAMS` · `BANK_REQUIRED` · `BANK_NOT_FOUND` · `BANK_EXISTS` ·
`DUPLICATE_BATCH` · `BANK_ERROR` · `RENDER_FAILED` · `FILE_NOT_FOUND` · `INTERNAL_ERROR`

`DUPLICATE_BATCH` deserves a note: applying the same batch twice would double-count a word's
attempts and corrupt streaks, so it is refused unless the caller explicitly passes
`allow_duplicate: true`. Guard rails over convenience.

## Scoring (fixed, documented, tested)

| Case | Score | Error type |
| --- | --- | --- |
| exact spelling, or any branch of a slash synonym | **1** | — |
| word off by 1–2 letters but recognisable (3–4 letter words: 1 letter) | **0.5** | spelling |
| unrecognisable / blank | **0** | unknown / blank |
| phrase missing a word | **0** | phrase-missing |
| phrase with extra word | **0** | phrase-other |
| phrase words all right, wrong order | **0** | phrase-order |

Half marks still count as an error (streak → 0, entry → wrong book). Details and edge cases:
[docs/scoring-rules.md](docs/scoring-rules.md).

## Repository layout

```
vocab-dictation/
├── README.md / README.zh-CN.md
├── SKILL.md                  # agent-facing contract (front matter + workflow)
├── skill.yaml                # machine-readable skill config (actions/IO/entrypoints)
├── pyproject.toml
├── src/vocab_dictation/
│   ├── core.py               # scoring kernel (pure, no I/O)
│   ├── bank.py               # xlsx bank: init/add/list/update/stats/sample/shuffle_all
│   ├── grading.py            # preview_grading / apply_grading (+ duplicate guard)
│   ├── rendering.py          # quiz & report PDFs + self-checks
│   ├── prepare.py            # phone-photo pre-processing (optional extra)
│   ├── api.py                # ACTION_SPECS + dispatch + capabilities
│   ├── cli.py                # vocabdict
│   ├── http_server.py        # POST /call, GET /capabilities, /health
│   ├── mcp_server.py         # MCP stdio (tool: vocab_dictation)
│   └── __init__.py           # VocabDictation facade
├── schemas/
│   ├── request.schema.json   # envelope contract
│   ├── response.schema.json
│   ├── tool.openai.json      # generated: OpenAI function declaration
│   ├── tool.anthropic.json   # generated: Anthropic tool declaration
│   └── capabilities.json     # generated: full action catalogue
├── prompts/
│   ├── extract_items.md      # notebook photo → items JSON
│   └── read_submission.md    # answer sheet → graded JSON (verbatim transcription)
├── docs/                     # quickstart / api-reference / integration / scoring-rules
├── examples/                 # 4 runnable examples
├── assets/sample_items.json  # 19 public sample entries, no private data
├── scripts/export_tool_schemas.py
└── tests/                    # 76 tests: judge / bank / grading / api / protocols / render / schemas
```

## What the LLM still has to do

This package deliberately does **not** ship OCR. Your model reads the photo; the repo gives it
a strict contract to answer in:

- `prompts/extract_items.md` — colour/annotation rules (black main word, blue extensions,
  red circle = rare sense, red wavy = key word), slash synonyms = one item, `=` chains split
  per member with all members flagged, uncertain readings must be marked.
- `prompts/read_submission.md` — **verbatim** transcription, never autocorrect spelling.

That split is the point: vision stays in the model, arithmetic and bookkeeping stay in code.

## Tests

```bash
pip install -e ".[dev]"
pytest            # 76 passed
```

Covers scoring boundaries, dedupe, scope filters, shuffle coverage, streak/clear lifecycle,
duplicate-batch guard, the envelope and every error code, CLI exit codes, MCP handshake,
HTTP round-trip incl. 401, and PDF self-check on both artifacts.

## Roadmap

- [ ] SQLite backend as an alternative to xlsx (for multi-user apps)
- [ ] Fuzzy matching for common L1 interference patterns (e.g. `-ance`/`-ence`)
- [ ] Optional SM-2 style scheduling on top of the current two-strike rule
- [ ] Localisation of the PDF layout (A4 vs Letter)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Scoring-rule changes must update code, docs and tests together.

## License

MIT — see [LICENSE](LICENSE).

> Repository: <https://github.com/karl-bro/AAAvocabDictation>. The repo name is `AAAvocabDictation`,
> while the package and module are `vocab-dictation` / `vocab_dictation`. If you fork under another
> account, update `pyproject.toml`, `skill.yaml` and the `$id` values under `schemas/`.
