# AI Buyer Assistant

A local product-selection assistant for artificial flowers and home décor. It combines catalogue search, multilingual embeddings, cross-encoder reranking and a Qwen model that chooses between search, product lookup and clarification.

## Quick start

Python 3.11 or 3.12. The bundled demo runs without third-party packages or model downloads:

```bash
python cli.py --demo search "浅粉色简约花束" --color 浅粉色 --form 花束 --currency GBP --max-price 10 --max-height-cm 40
python cli.py --demo details P0001
```

The 120 demo products are synthetic. Prices are GBP per item, not supplier quotes. Exact filters exclude missing attributes. Search terms affect ranking; use explicit flags for hard constraints. Colour and form filters use exact catalogue values.

## Neural search and chat

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python download_catalog.py
python cli.py --backend neural --rerank search "浅粉色、简约的仿真花"
python cli.py --backend neural --rerank chat
```

Activate the virtual environment before installing dependencies. For CUDA training, install a suitable PyTorch build for your machine first.

The downloader streams Home and Kitchen metadata from [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/), filters flower and plant titles, and saves up to 300 records in `data/public_products_raw.jsonl`. It scans at most 30,000 records per run and skips saved IDs. Increase `MAX_SCAN` in `download_catalog.py` if too few records are found. The source catalogue is downloaded separately and is not redistributed here.

Models download on first use:

| Stage | Model |
| --- | --- |
| Retrieval | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Reranking | `BAAI/bge-reranker-base` |
| Tool selection and answers | `Qwen/Qwen2.5-0.5B-Instruct` |

Inference runs on CPU. Models are cached in `models/`; set `BUYER_MODEL_CACHE` to reuse an existing cache. Model weights are excluded from Git. The lexical backend is a small offline baseline, not embedding search.

Chat accepts Chinese questions and asks for a product ID when needed. Type `quit` to exit. Tool names and arguments are validated before execution, and lookup IDs must appear in the user's message. Answers include product IDs and are prompted to use only retrieved evidence.

## LoRA experiment

The included dataset has 12 training and 6 evaluation examples covering lookup, search and clarification. These are small synthetic tool-routing examples, not a recommendation benchmark.

```bash
python evaluate_finetune.py --output results/base.json
python finetune_agent.py
python evaluate_finetune.py --adapter models/agent_lora --output results/lora.json
python cli.py --demo chat --adapter models/agent_lora
```

Training requires CUDA and runs one epoch with rank-4 LoRA on the query and value projections. Prompt tokens are masked from the loss. The saved adapter is loaded explicitly for evaluation and chat. Evaluation reports valid-decision rate, action accuracy and exact argument accuracy without executing tools. Search argument matching is strict string matching; semantically equivalent rewrites can score as incorrect.

## Layout

| Files | Purpose |
| --- | --- |
| `cli.py`, `service.py`, `catalog.py` | Commands, filtering and catalogue validation |
| `retrieve.py`, `rerank.py` | Embedding retrieval and cross-encoder scoring |
| `agent.py`, `local_llm.py`, `tools.py` | Tool decisions and local generation |
| `finetune_agent.py`, `evaluation.py`, `evaluate_finetune.py` | Adapter training and routing evaluation |
| `main.py`, `rag.py` | Original structured-filter and RAG demonstrations |
| `tests/` | Offline regression tests |

Custom catalogues can be passed with `--catalog path.jsonl`. Each record needs `parent_asin` (or `id`) and a title or name; optional fields include features, description, details and price. Per-item budget filtering requires explicit `currency` and `price_basis: "per_item"`. Heights must be numeric `height_cm`; dimensions embedded in free text are not inferred.

## Checks and limits

```bash
python -m unittest discover -s tests -v
```

The offline tests cover budget and dimension filtering, missing attributes, catalogue errors, unknown IDs, malformed tool calls, clarification and evaluation scoring. GitHub Actions runs them on Python 3.11 and 3.12.

Public catalogue prices are historical USD values with varying pack sizes. They cannot establish current prices, availability or GBP per-item budgets. Neural scores measure relevance, not compliance with every requirement. Chat does not automatically turn natural-language budgets into hard filters; use the search flags for those checks. Generated answers can still be wrong. There is no image analysis, live supplier integration or purchasing workflow.

Related project: [Environmental Language Model](https://github.com/Yulin2628/environmental-language-model).
