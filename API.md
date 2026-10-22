# Local planning API

```bash
python -m pip install -r requirements-planner.txt
python -m procurement.api --quotes data/procurement/quotes.json --database local/plans.sqlite --port 8765
```

The API listens on `127.0.0.1` only. Its example quotes are synthetic and valid during October-November 2026; outside that period, provide a current quote snapshot. Offline scenario replay is available through `cli.py --as-of`, not through HTTP request date overrides.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Version and health information |
| POST | `/plans` | Validate a brief, optimize, and persist a verified optimal draft |
| GET | `/plans/{id}` | Return snapshots, status, version and review events |
| POST | `/plans/{id}/review` | Approve or reject the expected draft version |

Requests and responses use JSON. `POST /plans` requires `Idempotency-Key`. The body is `{"brief": {...}}`; use the brief in `data/procurement/brief.json` as a complete example. To construct a request file:

```bash
python -c "import json; from pathlib import Path; Path('local/request.json').write_text(json.dumps({'brief':json.loads(Path('data/procurement/brief.json').read_text())}))"
curl -X POST http://127.0.0.1:8765/plans -H "Content-Type: application/json" -H "Idempotency-Key: demo-order-1" --data-binary @local/request.json
```

An optimal new draft returns 201 with `plan`, `record` and `replayed: false`. A retry with the same key and inputs returns 200 with the same record ID and `replayed: true`. Read `record.id` and `record.version` from the response before review:

```bash
curl -X POST http://127.0.0.1:8765/plans/RECORD_ID/review -H "Content-Type: application/json" --data '{"action":"approve","expected_version":1}'
```

Approval changes local state to `approved`, version 2; it does not place an order. Use `reject` for the alternative terminal transition. The review date is the server's current UTC date. A plan that now misses its original delivery date, uses expired quotes or references a changed quote snapshot must be replanned.

| Status | Meaning |
| --- | --- |
| 200 | Read, retry or successful review |
| 201 | New draft created |
| 400 | Malformed/missing/unsupported input |
| 404 | Unknown plan or route |
| 409 | Idempotency conflict, stale version, changed quotes or stale approval |
| 413 | Request body outside the supported size |
| 422 | No persistable optimal plan; inspect `plan.status` and its reasons |
| 503 | Planner admission or storage temporarily unavailable |

The API is unauthenticated and intended for local demonstration. See [the design](DESIGN.md) for model assumptions, transaction behavior and limits.
