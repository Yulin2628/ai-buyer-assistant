"""Recompute saved small-case oracle results and verify exact order accounting."""
import copy
import math
from pathlib import Path
import statistics

from evaluate_planner import exhaustive, check_allocation_independently
from procurement.application import load_json
from procurement.schema import digest, money
from procurement.verify import verify_plan


def main():
    report = load_json(Path("results/planner_evaluation.json"))
    summary = report["summary"]
    rows = report["cases"]
    assert len(rows) == summary["cases"] == 80
    agreements = feasible = baseline_feasible = baseline_optimal = combinations = metamorphic = 0
    excess = []
    for row in rows:
        case = row["case"]
        brief, quotes, as_of = case["brief"], case["quotes"], case["as_of"]
        assert digest(case) == row["input_sha256"]
        expected = exhaustive(brief, quotes, as_of)
        assert expected == row["oracle"]
        combinations += expected["enumerated_allocations"]
        optimum = expected["minimum_minor"]
        if optimum is None:
            agreement = row["milp"]["status"] == "infeasible"
        else:
            feasible += 1
            assert check_allocation_independently(brief, quotes, as_of, row["milp"])
            verify_plan(brief, quotes, row["milp"], as_of)
            agreement = row["milp"]["status"] == "optimal" and row["milp"]["accounting"]["total_minor"] == optimum
            if row["greedy"] is not None:
                baseline_feasible += 1
                assert check_allocation_independently(brief, quotes, as_of, row["greedy"])
                cost = row["greedy"]["accounting"]["total_minor"]
                baseline_optimal += cost == optimum
                excess.append(cost-optimum)
        agreements += agreement
        assert row["agreement"] == agreement
        for transformed in row["metamorphic_checks"]:
            name = transformed["transformation"]
            changed_brief, changed_quotes = copy.deepcopy(brief), copy.deepcopy(quotes)
            if name == "larger_budget":
                changed_brief["budget"] = f'{(money(brief["budget"])+1000)/100:.2f}'
            elif name == "later_deadline":
                changed_brief["deadline_days"] += 1
            elif name == "more_stock":
                for offer in changed_quotes["offers"]:
                    if offer["stock_packs"] is not None:
                        offer["stock_packs"] += 1
            else:
                assert name == "reordered_offers"
                changed_quotes["offers"].reverse()
            plan = transformed["result"]
            changed_optimum = exhaustive(changed_brief, changed_quotes, as_of)["minimum_minor"]
            if changed_optimum is None:
                assert plan["status"] == "infeasible"
            else:
                assert plan["status"] == "optimal" and plan["accounting"]["total_minor"] == changed_optimum
                assert check_allocation_independently(changed_brief, changed_quotes, as_of, plan)
                verify_plan(changed_brief, changed_quotes, plan, as_of)
            if optimum is not None:
                assert changed_optimum is not None and changed_optimum <= optimum
            if name == "reordered_offers":
                assert changed_optimum == optimum
            assert transformed["passed"]
            metamorphic += 1
    assert agreements == summary["oracle_agreements"] == 80
    assert feasible == summary["oracle_feasible"]
    assert 80-feasible == summary["oracle_infeasible"]
    assert baseline_feasible == summary["greedy_feasible_on_oracle_feasible"]
    assert baseline_optimal == summary["greedy_optimal_on_oracle_feasible"]
    assert combinations == summary["enumerated_allocations"]
    assert metamorphic == summary["metamorphic_checks"] == summary["metamorphic_passed"] == 320
    assert len(excess) == summary["comparable_greedy_cases"]
    assert math.isclose(statistics.mean(excess), summary["mean_greedy_excess_minor_on_common"])
    times = sorted(row["solve_ms"] for row in rows)
    assert math.isclose(statistics.median(times), summary["median_solve_ms"])
    assert math.isclose(times[math.ceil(.95*len(times))-1], summary["p95_solve_ms_across_cases"])
    demo = report["demo"]
    verify_plan(demo["brief"], demo["quotes"], demo["optimal"], "2026-10-22")
    for plan in demo["frontier"]["plans"]:
        verify_plan(demo["brief"], demo["quotes"], plan, "2026-10-22")
    scaling = load_json(Path("results/planner_scaling.json"))
    for scenario in scaling["scenarios"]:
        assert digest(scenario["inputs"]) == scenario["input_sha256"]
        assert math.isclose(statistics.median(row["planning_ms"] for row in scenario["runs"]), scenario["median_ms"])
        for row in scenario["runs"]:
            if row["plan"]["status"] in ("optimal", "feasible_not_proven"):
                inputs = scenario["inputs"]
                verify_plan(inputs["brief"], inputs["quotes"], row["plan"], inputs["as_of"])
    print("Verified 80 enumerated cases, 320 transformed cases, the demo frontier and scaling records.")


if __name__ == "__main__":
    main()
