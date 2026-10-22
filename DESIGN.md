# Procurement decision support

The existing catalogue search finds relevant products. The new planner works on a separate, normalized quote snapshot because historical catalogue prices do not establish pack sizes, supplier shipping, stock or quote validity. A structured brief must specify its currency, total budget, deadline and requirement quantities; unsupported or missing fields raise an error. Free-text descriptions do not become executable instructions or hard constraints. Natural-language constraint extraction is not claimed.

## Integer model

For each eligible offer/requirement edge, integer `x[o,l]` counts packs assigned to that line. Binary `z[o]` indicates an active offer, and binary `y[s]` indicates an active supplier. Only offers with compatible attributes, known stock, known lead time, current quote dates and matching currency enter the allocation edges.

The objective minimizes `sum(pack_price[o] * x[o,l]) + sum(shipping[s] * y[s])`, using integer minor currency units. GBP, USD and EUR are supported separately; currencies are never converted. Constraints enforce:

- Required units per line, bounded by any explicitly permitted surplus.
- Aggregate offer stock shared across all lines.
- Aggregate minimum packs whenever an offer is used.
- Supplier activation and one fixed shipping charge per active supplier.
- A supplier-count cap when supplied, and the complete budget including shipping.

Offer lead times are end-to-end delivery durations in whole days. Shipping is a known flat supplier fee per order. Tax, duties, quantity discounts, multi-warehouse inventory and route-dependent freight are outside this model. Pack prices are pack prices rather than assumed per-item catalogue prices.

SciPy's [milp](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html) delegates to HiGHS. The relative MIP gap is zero and the default solve time limit is three seconds. An independently feasible incumbent at the limit is `feasible_not_proven`, not `optimal`; it does not enter the approval workflow. An unresolved result is not represented as infeasibility. The configured time limit governs the solver, not validation, model construction or an optional diagnostic solve.

Every proposed order is reconstructed with integer arithmetic and checked against the input records independently of the constraint matrix. The checker recalculates quantities, aggregate MOQ/stock, shipping and budget. Hashes bind the result to the brief and quote snapshots. This verifies feasibility and accounting; optimality comes from solver status or the separate small-case exhaustive reference.

## Alternatives and infeasibility

The frontier solves the same model under each distinct eligible delivery cap, then removes dominated cost/lead-time points. It supports at most 20 caps and retains a partial status if a solve is unresolved. Cost ties may have multiple allocations; a unique ordering of equivalent products is not guaranteed.

No hard requirement is relaxed silently. An infeasible order can receive a minimum-required-cost diagnostic from a separate solve with a larger budget. This diagnostic remains a separate result, and the user's rejected order is not replaced by an over-budget recommendation. Infeasibility explanations are not an irreducible-conflict certificate or a complete diagnosis of every conflicting constraint.

## Review state and replay

Only verified optimal plans are stored as drafts. The body contains the exact brief, quote snapshot, planning date and solver result. Idempotency keys are unique: a repeated key with the same inputs returns the existing record; reusing it for different inputs returns a conflict. Infeasible/unresolved attempts are not persisted and may be recomputed on retry.

SQLite `BEGIN IMMEDIATE` serializes writers. Drafts transition once to approved or rejected using an expected version. Two reviewers cannot both transition version 1. Body data is not edited by the API; review events retain the body hash and new version. Connections are closed after each transaction.

Approval requires the current quote snapshot to match the stored snapshot, all quotes to remain valid, and the planned delivery duration to fit the original remaining deadline. The HTTP API uses its UTC date; callers cannot backdate requests. The CLI's `--as-of` is an explicit offline replay option.

These are local review records. Approval does not reserve stock, transmit a purchase order or execute payment. Hashes identify snapshots and detect accidental inconsistency; they are not signatures or protection against a database administrator. There is no authenticated reviewer identity or role-based authorization.

## API boundaries

The standard-library HTTP server binds only to `127.0.0.1`. It accepts JSON bodies up to 64 KiB, applies schema validation and limits planning/review POST work to one admitted request at a time. A busy request receives 503 and can retry. This is a local prototype without production authentication, TLS termination, distributed workers or load testing.

The supported input bounds are 500 offers, 100 suppliers and 12 requirement lines. These are input limits rather than guaranteed worst-case latency bounds. The small reference checks and larger synthetic timing fixtures are described separately in [the evaluation](results/EVALUATION.md).
