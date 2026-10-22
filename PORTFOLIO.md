# Portfolio positioning

| Project | Main emphasis |
| --- | --- |
| AI Buyer Assistant | Constraint optimization, exact order accounting, transactional workflows and API reliability |
| Environmental Language Model | Transformer internals, attention/KV-cache implementation and inference benchmarking |
| CMU AG News | Prompt/LoRA comparisons, controlled model experiments and error analysis |

## Suggested CV bullets

- Extended a retrieval-based buyer assistant with a mixed-integer procurement planner covering pack sizes, minimum orders, shared stock, supplier shipping, delivery limits and budget constraints; generated non-dominated cost/delivery alternatives.
- Built a local HTTP API with transactional SQLite persistence, idempotency keys, versioned review transitions and quote-snapshot validation; prevented stale or conflicting approvals and retained exact order accounting and review events.
- Cross-checked 80 synthetic instances against exhaustive enumeration and verified 320 constraint transformations; solved a 3,520-variable, 500-offer scenario in 214 ms median across three local runs.

The test figures describe synthetic algorithm/workflow checks. They do not establish recommendation accuracy, real savings, live inventory availability or production API capacity. The legacy neural retrieval and small LoRA example remain separate; this upgrade does not claim a newly measured language-model improvement.
