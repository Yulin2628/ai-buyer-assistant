"""Synthetic algorithm checks against independent exhaustive enumeration."""
import argparse
from collections import Counter
import copy
from datetime import date
from decimal import Decimal
from fractions import Fraction
import itertools
import json
import math
from pathlib import Path
import platform
import random
import statistics
import time

from procurement.application import load_json
from procurement.schema import digest, exclusion_reasons, money
from procurement.solver import frontier, solve
from procurement.verify import account

ROOT = Path(__file__).resolve().parent
AS_OF = "2026-10-22"


def oracle_options(brief, snapshot, as_of):
    """Reimplement eligibility from the documented spec, without solver helpers."""
    today = date.fromisoformat(as_of)
    suppliers = {supplier["id"]: supplier for supplier in snapshot["suppliers"]}
    choices = []
    for offer in snapshot["offers"]:
        compatible = []
        for line in brief["lines"]:
            eligible = (offer["currency"] == suppliers[offer["supplier_id"]]["currency"] == brief["currency"]
                        and offer["stock_packs"] is not None and offer["lead_days"] is not None
                        and offer["lead_days"] <= brief["deadline_days"]
                        and offer["quoted_on"] is not None and offer["valid_until"] is not None)
            if eligible:
                eligible = date.fromisoformat(offer["quoted_on"]) <= today <= date.fromisoformat(offer["valid_until"])
            for key, value in line["attributes"].items():
                eligible = eligible and offer["attributes"].get(key, "").lower().strip() == value.lower().strip()
            if "max_height_cm" in line:
                eligible = eligible and offer.get("height_cm") is not None and offer["height_cm"] <= line["max_height_cm"]
            cap = min(offer["stock_packs"] or 0,
                      (line["quantity"] + line.get("max_surplus_units", 0)) // offer["pack_size"]) if eligible else 0
            compatible.append(range(cap + 1))
        choices.append([allocation for allocation in itertools.product(*compatible)
                        if sum(allocation) == 0 or offer["min_packs"] <= sum(allocation) <= (offer["stock_packs"] or 0)])
    return choices


def oracle_cost(brief, snapshot, allocation):
    """Allocation is an offer-by-line integer tuple, with zero for unused offers."""
    delivered = [0] * len(brief["lines"])
    subtotal = 0
    active_suppliers = set()
    for offer, counts in zip(snapshot["offers"], allocation):
        packs = sum(counts)
        if packs:
            active_suppliers.add(offer["supplier_id"])
            subtotal += packs * int(Decimal(str(offer["pack_price"])) * 100)
        for li, amount in enumerate(counts):
            delivered[li] += amount * offer["pack_size"]
    if len(active_suppliers) > brief.get("max_suppliers", 100):
        return None
    if any(not line["quantity"] <= count <= line["quantity"] + line.get("max_surplus_units", 0)
           for line, count in zip(brief["lines"], delivered)):
        return None
    shipping = sum(int(Decimal(str(supplier["shipping"])) * 100)
                   for supplier in snapshot["suppliers"] if supplier["id"] in active_suppliers)
    total = subtotal + shipping
    return total if total <= int(Decimal(str(brief["budget"])) * 100) else None


def exhaustive(brief, snapshot, as_of):
    options = oracle_options(brief, snapshot, as_of)
    best = None
    combinations = 0
    for allocation in itertools.product(*options):
        combinations += 1
        total = oracle_cost(brief, snapshot, allocation)
        if total is not None and (best is None or total < best):
            best = total
    return {"minimum_minor": best, "enumerated_allocations": combinations}


def check_allocation_independently(brief, snapshot, as_of, plan):
    allocation = [[0] * len(brief["lines"]) for _ in snapshot["offers"]]
    indices = {offer["id"]: i for i, offer in enumerate(snapshot["offers"])}
    line_indices = {line["id"]: i for i, line in enumerate(brief["lines"])}
    for row in plan["allocations"]:
        allocation[indices[row["offer_id"]]][line_indices[row["line_id"]]] += row["packs"]
    choices = oracle_options(brief, snapshot, as_of)
    if any(tuple(row) not in allowed for row, allowed in zip(allocation, choices)):
        return False
    return oracle_cost(brief, snapshot, allocation) == plan["accounting"]["total_minor"]


def greedy(brief, snapshot, as_of):
    """Eligible cheapest-unit-price baseline; hard-check the completed order."""
    suppliers = {row["id"]: row for row in snapshot["suppliers"]}
    used = Counter()
    allocations = []
    for line in brief["lines"]:
        remaining = line["quantity"]
        delivered = 0
        offers = [offer for offer in snapshot["offers"] if not exclusion_reasons(
            offer, suppliers[offer["supplier_id"]], line, brief, as_of)]
        offers.sort(key=lambda offer: (Fraction(money(offer["pack_price"]), offer["pack_size"]), offer["id"]))
        for offer in offers:
            if remaining <= 0:
                break
            minimum = max(0, offer["min_packs"] - used[offer["id"]])
            wanted = max(minimum, (remaining + offer["pack_size"] - 1) // offer["pack_size"])
            available = offer["stock_packs"] - used[offer["id"]]
            packs = min(wanted, available)
            if packs <= 0 or packs < minimum:
                continue
            if delivered + packs * offer["pack_size"] > line["quantity"] + line.get("max_surplus_units", 0):
                packs = (line["quantity"] + line.get("max_surplus_units", 0) - delivered) // offer["pack_size"]
            if packs <= 0 or packs < minimum:
                continue
            allocations.append({"offer_id": offer["id"], "line_id": line["id"], "packs": packs})
            used[offer["id"]] += packs
            delivered += packs * offer["pack_size"]
            remaining = line["quantity"] - delivered
    try:
        return {"allocations": allocations, "accounting": account(brief, snapshot, allocations, as_of)}
    except ValueError:
        return None


def generated_cases(seed=20261022, count=80):
    rng = random.Random(seed)
    cases = []
    for case in range(count):
        suppliers = [{"id": f"S{s}", "currency": "GBP", "shipping": f'{rng.randint(0, 400)/100:.2f}'} for s in range(3)]
        offers = []
        for index in range(4):
            offers.append({"id": f"O{index}", "supplier_id": f"S{rng.randrange(3)}", "product_id": f"P{index}",
                           "attributes": {"color": rng.choice(["pink", "white"])}, "currency": "GBP",
                           "pack_price": f'{rng.randint(20, 600)/100:.2f}', "pack_size": rng.randint(1, 4),
                           "min_packs": rng.randint(1, 2), "stock_packs": rng.randint(1, 3),
                           "lead_days": rng.randint(1, 7), "quoted_on": "2026-10-01", "valid_until": "2026-11-01", "height_cm": 30})
        if case % 7 == 0:
            offers[0]["valid_until"] = "2026-10-20"
        if case % 11 == 0:
            offers[1]["stock_packs"] = None
        if case % 13 == 0:
            offers[2]["currency"] = "USD"
        lines = [{"id": f"L{i}", "quantity": rng.randint(2, 7),
                  "attributes": {} if case % 5 == 0 else {"color": ("pink" if i == 0 else "white")},
                  "max_surplus_units": rng.randint(0, 3)} for i in range(1 + case % 2)]
        brief = {"schema_version": 1, "currency": "GBP", "budget": f'{rng.randint(5, 30):.2f}',
                 "deadline_days": rng.randint(3, 7), "lines": lines}
        if case % 4 == 0:
            brief["max_suppliers"] = 1
        cases.append({"id": f"enumerated-{case:03}", "brief": brief,
                      "quotes": {"schema_version": 1, "source": "synthetic_enumeration_fixture",
                                 "suppliers": suppliers, "offers": offers}, "as_of": AS_OF})
    return cases


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "local/planner_evaluation.json")
    args = parser.parse_args()
    import scipy
    cases = generated_cases()
    # Import and solver initialization are outside per-case latency measurements.
    solve(cases[0]["brief"], cases[0]["quotes"], AS_OF, diagnose=False)
    results = []
    for case in cases:
        brief, quotes = case["brief"], case["quotes"]
        oracle = exhaustive(brief, quotes, AS_OF)
        start = time.perf_counter()
        plan = solve(brief, quotes, AS_OF, diagnose=False)
        elapsed = (time.perf_counter() - start) * 1000
        baseline = greedy(brief, quotes, AS_OF)
        expected = oracle["minimum_minor"]
        agreement = (plan["status"] == "infeasible" if expected is None else
                     plan["status"] == "optimal" and plan["accounting"]["total_minor"] == expected
                     and check_allocation_independently(brief, quotes, AS_OF, plan))
        transformations = []
        for name in ("larger_budget", "later_deadline", "more_stock", "reordered_offers"):
            altered, catalog = copy.deepcopy(brief), copy.deepcopy(quotes)
            if name == "larger_budget":
                altered["budget"] = f'{(money(brief["budget"])+1000)/100:.2f}'
            elif name == "later_deadline":
                altered["deadline_days"] += 1
            elif name == "more_stock":
                for offer in catalog["offers"]:
                    if offer["stock_packs"] is not None:
                        offer["stock_packs"] += 1
            else:
                catalog["offers"].reverse()
            changed = solve(altered, catalog, AS_OF, diagnose=False)
            passed = changed["status"] in ("optimal", "infeasible")
            if expected is not None:
                passed = passed and changed["status"] == "optimal" and changed["accounting"]["total_minor"] <= expected
            if name == "reordered_offers":
                passed = passed and ((expected is None and changed["status"] == "infeasible") or
                                    (expected is not None and changed.get("accounting", {}).get("total_minor") == expected))
            transformations.append({"transformation": name, "passed": passed, "result": changed})
        results.append({"case": case, "input_sha256": digest(case), "oracle": oracle,
                        "milp": plan, "greedy": baseline, "agreement": agreement,
                        "solve_ms": elapsed, "metamorphic_checks": transformations})
    feasible = [row for row in results if row["oracle"]["minimum_minor"] is not None]
    common = [row for row in feasible if row["greedy"] is not None]
    times = sorted(row["solve_ms"] for row in results)
    summary = {"cases": len(results), "oracle_agreements": sum(row["agreement"] for row in results),
               "oracle_feasible": len(feasible), "oracle_infeasible": len(results)-len(feasible),
               "greedy_feasible_on_oracle_feasible": sum(row["greedy"] is not None for row in feasible),
               "greedy_optimal_on_oracle_feasible": sum(row["greedy"] is not None and row["greedy"]["accounting"]["total_minor"] == row["oracle"]["minimum_minor"] for row in feasible),
               "comparable_greedy_cases": len(common),
               "mean_greedy_excess_minor_on_common": statistics.mean(row["greedy"]["accounting"]["total_minor"]-row["oracle"]["minimum_minor"] for row in common) if common else None,
               "enumerated_allocations": sum(row["oracle"]["enumerated_allocations"] for row in results),
               "metamorphic_checks": sum(len(row["metamorphic_checks"]) for row in results),
               "metamorphic_passed": sum(item["passed"] for row in results for item in row["metamorphic_checks"]),
               "median_solve_ms": statistics.median(times), "p95_solve_ms_across_cases": times[math.ceil(.95*len(times))-1]}
    demo_brief = load_json(ROOT / "data/procurement/brief.json")
    demo_quotes = load_json(ROOT / "data/procurement/quotes.json")
    report = {"schema_version": 1, "seed": 20261022, "python": platform.python_version(), "scipy": scipy.__version__,
              "summary": summary, "cases": results,
              "demo": {"brief": demo_brief, "quotes": demo_quotes,
                       "greedy": greedy(demo_brief, demo_quotes, AS_OF),
                       "optimal": solve(demo_brief, demo_quotes, AS_OF),
                       "frontier": frontier(demo_brief, demo_quotes, AS_OF)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    if summary["oracle_agreements"] != len(results) or summary["metamorphic_passed"] != summary["metamorphic_checks"]:
        raise SystemExit("Evaluation disagreement; inspect the retained case records")


if __name__ == "__main__":
    main()
