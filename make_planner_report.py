"""Render saved procurement measurements into reviewable tables and figures."""
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from procurement.application import load_json

ROOT = Path(__file__).resolve().parent


def main():
    results = ROOT / "results"
    report = load_json(results / "planner_evaluation.json")
    scaling = load_json(results / "planner_scaling.json")
    summary, demo = report["summary"], report["demo"]
    greedy, optimized = demo["greedy"]["accounting"], demo["optimal"]["accounting"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    x = np.arange(2)
    items = [greedy, optimized]
    subtotals = [item["subtotal_minor"] / 100 for item in items]
    freight = [item["shipping_minor"] / 100 for item in items]
    axes[0].bar(x, subtotals, label="Goods", color="#477a9c")
    axes[0].bar(x, freight, bottom=subtotals, label="Supplier shipping", color="#bd703e")
    for i, item in enumerate(items):
        axes[0].text(i, item["total_minor"]/100+1, f'GBP {item["total_minor"]/100:.0f}', ha="center")
    axes[0].set(xticks=x, xticklabels=["Cheapest-unit greedy", "Order optimizer"],
                ylabel="Total order cost (GBP)", title="One synthetic shipping-cost scenario", ylim=(0,125))
    axes[0].legend(frameon=False)
    plans = demo["frontier"]["plans"]
    days = [plan["accounting"]["lead_days"] for plan in plans]
    totals = [plan["accounting"]["total_minor"]/100 for plan in plans]
    axes[1].plot(days, totals, "o-", color="#477a9c", linewidth=2, markersize=8)
    for day, total in zip(days, totals):
        axes[1].annotate(f"GBP {total:.0f}", (day,total), xytext=(0,10), textcoords="offset points", ha="center")
    axes[1].set(xlabel="Delivery lead time (days)", ylabel="Order cost (GBP)",
                title="Non-dominated cost / delivery alternatives", xticks=days, ylim=(72,100))
    fig.savefig(results / "decision_frontier.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12,4.8), layout="constrained")
    milp = [summary["oracle_feasible"], summary["oracle_feasible"]]
    baseline = [summary["greedy_feasible_on_oracle_feasible"], summary["greedy_optimal_on_oracle_feasible"]]
    axes[0].bar(x-.17, milp, .32, label="MILP", color="#477a9c")
    axes[0].bar(x+.17, baseline, .32, label="Greedy", color="#bd703e")
    axes[0].set(xticks=x, xticklabels=["Returned feasible order", "Returned minimum cost"],
                ylabel="Cases", title=f'Only the {summary["oracle_feasible"]} oracle-feasible cases', ylim=(0,32))
    for i in range(2):
        axes[0].text(i-.17, milp[i]+.6, str(milp[i]), ha="center")
        axes[0].text(i+.17, baseline[i]+.6, str(baseline[i]), ha="center")
    axes[0].legend(frameon=False)
    cases = scaling["scenarios"]
    medians = [case["median_ms"] for case in cases]
    minimum = [min(row["planning_ms"] for row in case["runs"]) for case in cases]
    maximum = [max(row["planning_ms"] for row in case["runs"]) for case in cases]
    axes[1].errorbar(range(3), medians,
                     yerr=[np.array(medians)-minimum, np.array(maximum)-medians],
                     marker="o", color="#477a9c", capsize=4)
    axes[1].set(xticks=range(3), xticklabels=[f'{case["offers"]} / {case["lines"]}' for case in cases],
                xlabel="Offers / requirement lines", ylabel="Full planning time (ms)",
                title="Seeded synthetic scaling: median and range")
    fig.savefig(results / "planner_checks.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    lines = ["# Procurement planner evaluation", "",
             "All quotes, supplier fees and requirements in this evaluation are synthetic. The experiment measures optimization and rule handling, not real-world purchasing savings, recommendation relevance or LLM accuracy. No supplier orders are placed.", "",
             "## Small-case reference check", "",
             f'{summary["cases"]} seeded instances contain four offers, three suppliers and one or two requirement lines. Independent exhaustive enumeration reimplements eligibility and accounting without the solver matrices. It enumerates {summary["enumerated_allocations"]:,} allocation combinations in total. This is a small reference suite, not a proof for every input.', "",
             "| Outcome | Count |", "| --- | ---: |",
             f'| MILP agreement with reference feasibility and minimum cost | {summary["oracle_agreements"]}/{summary["cases"]} |',
             f'| Oracle-feasible cases | {summary["oracle_feasible"]} |',
             f'| Oracle-infeasible cases | {summary["oracle_infeasible"]} |',
             f'| Feasible greedy orders on oracle-feasible cases | {summary["greedy_feasible_on_oracle_feasible"]}/{summary["oracle_feasible"]} |',
             f'| Minimum-cost greedy orders on oracle-feasible cases | {summary["greedy_optimal_on_oracle_feasible"]}/{summary["oracle_feasible"]} |',
             f'| Budget, delivery, stock and reorder transformations passed | {summary["metamorphic_passed"]}/{summary["metamorphic_checks"]} |', "",
             "The greedy baseline ranks eligible offers by unit price, fills each requirement in input order, then checks the complete order including shipping, MOQ, stock, supplier count and budget. It never presents a known constraint violation as a recommendation. It is already optimal on most feasible small cases; the optimizer mainly handles coupled choices and cases where local decisions fail.", "",
             "The transformed cases increase budget, relax the delivery limit, add known stock, or reorder offers. The verifier separately enumerates those transformed cases too. These are deterministic algorithm checks, not held-out customer evaluation. Input snapshots, hashes, raw solver statuses and allocations are retained in planner_evaluation.json.", "",
             f'The median full planning call across these small instances was {summary["median_solve_ms"]:.2f} ms; the 95th percentile across different instances was {summary["p95_solve_ms_across_cases"]:.2f} ms. Each case has one timing observation after a solver warmup. That percentile is not a repeated-serving latency estimate.', "",
             "## Shipping and delivery example", "",
             f'The supplied demo requires 24 pink stems and 12 pink bouquets. Cheapest-unit greedy totals GBP {greedy["total_minor"]/100:.2f}: GBP {greedy["subtotal_minor"]/100:.2f} of goods plus GBP {greedy["shipping_minor"]/100:.2f} shipping across two suppliers. The optimizer chooses a GBP {optimized["total_minor"]/100:.2f} single-supplier order, including GBP {optimized["shipping_minor"]/100:.2f} shipping. The GBP {(greedy["total_minor"]-optimized["total_minor"])/100:.2f} difference is one deliberately constructed scenario, not observed commercial savings.', "",
             "| Delivery days | Minimum feasible cost (GBP) |", "| ---: | ---: |"]
    for plan in plans:
        lines.append(f'| {plan["accounting"]["lead_days"]} | {plan["accounting"]["total_minor"]/100:.2f} |')
    lines += ["", "![Shipping and delivery](decision_frontier.png)", "", "## Scaling", "",
              "Each synthetic quote book receives one unmeasured warmup and three repeated planning calls. Timing includes validation, eligibility, matrix construction, MILP and exact post-solve verification. It excludes model loading, HTTP, SQLite and JSON file IO. The largest instances are not exhaustively enumerated; their optimality status comes from HiGHS with relative MIP gap set to zero.", "",
              "| Offers | Lines | Variables | Constraints | Median (ms) | Observed statuses |",
              "| ---: | ---: | ---: | ---: | ---: | --- |"]
    for case in cases:
        solver = case["runs"][0]["plan"]["solver"]
        statuses = ", ".join(row["plan"]["status"] for row in case["runs"])
        lines.append(f'| {case["offers"]} | {case["lines"]} | {solver["variables"]} | {solver["constraints"]} | {case["median_ms"]:.2f} | {statuses} |')
    lines += ["", f'Runtime: Python {scaling["python"]}, SciPy {scaling["scipy"]}; CPU: {scaling["cpu"]}. Laptop timings and three repeats do not establish deployment capacity or worst-case MILP complexity.', "",
              "![Reference checks and scaling](planner_checks.png)", "",
              "## Workflow regression coverage", "",
              "The suite covers exact money parsing, unsupported/missing input fields, pack rounding, aggregated MOQ/stock across lines, shipping charged once, supplier limits, expired/unknown/currency-incompatible offers, inert free-text instructions, independent plan verification, non-optimal solver status, idempotent creation, concurrent create/review, stale versions, quote changes, delayed approval, expiry and an HTTP create/retry/review round trip. It uses temporary SQLite databases and loopback sockets. Reviews change local state only; they do not contact suppliers.", "",
              "## Reproduce", "", "```bash", "python -m pip install -r requirements-planner.txt", "python -m unittest discover -s tests -v", "python evaluate_planner.py", "python benchmark_planner.py", "python verify_planner_results.py", "python -m pip install -r requirements-report.txt", "python make_planner_report.py", "```", "",
              "The report builder uses the saved records. Rerunning the evaluators overwrites local evaluation outputs; no training or real catalogue access is needed."]
    (results / "EVALUATION.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    largest = cases[-1]
    variables = largest["runs"][0]["plan"]["solver"]["variables"]
    portfolio = ["# Portfolio positioning", "",
             "| Project | Main emphasis |", "| --- | --- |",
             "| AI Buyer Assistant | Constraint optimization, exact order accounting, transactional workflows and API reliability |",
             "| Environmental Language Model | Transformer internals, attention/KV-cache implementation and inference benchmarking |",
             "| CMU AG News | Prompt/LoRA comparisons, controlled model experiments and error analysis |", "",
             "## Suggested CV bullets", "",
             "- Extended a retrieval-based buyer assistant with a mixed-integer procurement planner covering pack sizes, minimum orders, shared stock, supplier shipping, delivery limits and budget constraints; generated non-dominated cost/delivery alternatives.",
             "- Built a local HTTP API with transactional SQLite persistence, idempotency keys, versioned review transitions and quote-snapshot validation; prevented stale or conflicting approvals and retained exact order accounting and review events.",
             f'- Cross-checked 80 synthetic instances against exhaustive enumeration and verified 320 constraint transformations; solved a {variables:,}-variable, 500-offer scenario in {largest["median_ms"]:.0f} ms median across three local runs.', "",
             "The test figures describe synthetic algorithm/workflow checks. They do not establish recommendation accuracy, real savings, live inventory availability or production API capacity. The legacy neural retrieval and small LoRA example remain separate; this upgrade does not claim a newly measured language-model improvement."]
    (ROOT / "PORTFOLIO.md").write_text("\n".join(portfolio)+"\n", encoding="utf-8")
    print("Created two figures, evaluation report and portfolio notes.")


if __name__ == "__main__":
    main()
