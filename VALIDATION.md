# Validation

## Earlier neural and catalogue smoke checks

Checked locally on 21 October 2026 with Python 3.12.7.

- 11 offline regression tests passed; all Python files compiled.
- Embedding retrieval ran on 248 locally downloaded catalogue records, producing 384-dimensional vectors. Cross-encoder reranking returned 3 results from 5 candidates. This checks execution, not recommendation quality.
- Qwen base-model inference and loading an existing local LoRA adapter both completed on CPU.

Tool-routing results on the 6 included evaluation questions:

| Model | Valid decisions | Correct actions | Exact arguments |
| --- | --- | --- | --- |
| Qwen2.5-0.5B-Instruct | 3/6 | 1/6 | 1/6 |
| Same model + existing local adapter | 3/6 | 2/6 | 1/6 |

The existing adapter was trained before the prompt changes in this revision and is not redistributed. These numbers do not evaluate a newly trained adapter or establish a reliable improvement. The sample is too small for general conclusions. Invalid JSON, unknown tools and ungrounded lookup IDs are rejected before execution; a valid decision can still choose the wrong action.

The usable baseline is catalogue search with explicit filters. LLM routing and LoRA training remain experiments. Training was not rerun as part of this revision.

Neural smoke checks used the existing environment: PyTorch 2.13.0+cu126, Transformers 5.19.0, Sentence Transformers 6.1.0 and PEFT 0.21.2. Other dependency combinations have not been tested locally. CI separately checks the standard-library-only demo on Python 3.11 and 3.12.
