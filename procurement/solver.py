"""Integer pack allocation with supplier activation costs and explicit solver status."""
import copy
import math

from procurement.schema import (InputError, digest, exclusion_reasons, iso_date,
                                money, validate_brief, validate_quotes)
from procurement.verify import account, verify_plan


def solve(brief, snapshot, as_of, time_limit=3.0, diagnose=True):
    validate_brief(brief)
    validate_quotes(snapshot)
    iso_date(as_of, "as_of")
    if isinstance(time_limit, bool) or not isinstance(time_limit, (int, float)) or not math.isfinite(time_limit) or not 0 < time_limit <= 30:
        raise InputError("time_limit must be between 0 and 30 seconds")
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    suppliers = sorted(snapshot["suppliers"], key=lambda row: row["id"])
    offers = sorted(snapshot["offers"], key=lambda row: row["id"])
    lines = sorted(brief["lines"], key=lambda row: row["id"])
    supplier_index = {row["id"]: i for i, row in enumerate(suppliers)}
    edges = []
    rejected = []
    for oi, offer in enumerate(offers):
        supplier = suppliers[supplier_index[offer["supplier_id"]]]
        for li, line in enumerate(lines):
            reasons = exclusion_reasons(offer, supplier, line, brief, as_of)
            if reasons:
                rejected.append({"offer_id": offer["id"], "line_id": line["id"], "reasons": reasons})
            else:
                edges.append((oi, li))
    result = {"schema_version": 1, "as_of": as_of, "brief_sha256": digest(brief),
              "quotes_sha256": digest(snapshot), "excluded_edges": rejected,
              "solver": {"name": "scipy.optimize.milp / HiGHS", "time_limit_seconds": time_limit}}
    if not edges:
        return {**result, "status": "infeasible", "reason": "No eligible, current offers match the brief"}
    n, no, ns = len(edges), len(offers), len(suppliers)
    dimension = n + no + ns
    costs = np.zeros(dimension)
    upper = np.ones(dimension)
    for e, (oi, _) in enumerate(edges):
        costs[e] = money(offers[oi]["pack_price"])
        upper[e] = offers[oi]["stock_packs"]
    for si, supplier in enumerate(suppliers):
        costs[n + no + si] = money(supplier["shipping"])
    constraints = []
    def row(coefficients, lower=-np.inf, upper=np.inf):
        constraints.append((coefficients, lower, upper))
    for li, line in enumerate(lines):
        row({e: offers[oi]["pack_size"] for e, (oi, edge_li) in enumerate(edges) if edge_li == li},
            line["quantity"], line["quantity"] + line.get("max_surplus_units", 0))
    for oi, offer in enumerate(offers):
        selected = n + oi
        per_offer = {e: 1 for e, (edge_oi, _) in enumerate(edges) if edge_oi == oi}
        capacity = offer["stock_packs"] or 0
        row({**per_offer, selected: -capacity}, upper=0)
        row({**per_offer, selected: -offer["min_packs"]}, lower=0)
        si = supplier_index[offer["supplier_id"]]
        row({selected: 1, n + no + si: -1}, upper=0)
    for si, supplier in enumerate(suppliers):
        row({**{n + oi: -1 for oi, offer in enumerate(offers) if offer["supplier_id"] == supplier["id"]},
             n + no + si: 1}, upper=0)
    row({n + no + si: 1 for si in range(ns)}, upper=brief.get("max_suppliers", 100))
    row({i: value for i, value in enumerate(costs) if value}, upper=money(brief["budget"]))
    matrix = lil_matrix((len(constraints), dimension), dtype=float)
    for ri, (coefficients, _, _) in enumerate(constraints):
        for ci, value in coefficients.items():
            matrix[ri, ci] = value
    lower_bounds = np.array([item[1] for item in constraints])
    upper_bounds = np.array([item[2] for item in constraints])
    solution = milp(costs, integrality=np.ones(dimension), bounds=Bounds(np.zeros(dimension), upper),
                    constraints=LinearConstraint(matrix.tocsc(), lower_bounds, upper_bounds),
                    options={"time_limit": float(time_limit), "mip_rel_gap": 0.0})
    def finite_metric(name):
        value = getattr(solution, name, None)
        return float(value) if value is not None and math.isfinite(value) else None
    result["solver"].update({"status_code": int(solution.status), "message": solution.message,
                            "variables": dimension, "constraints": len(constraints),
                            "mip_gap": finite_metric("mip_gap"),
                            "dual_bound_minor": finite_metric("mip_dual_bound")})
    if solution.status == 2:
        result.update(status="infeasible", reason="No allocation satisfies all hard constraints")
        if diagnose and money(brief["budget"]) < 100_000_000:
            relaxed = copy.deepcopy(brief)
            relaxed["budget"] = "1000000.00"
            without_budget = solve(relaxed, snapshot, as_of, time_limit, diagnose=False)
            if without_budget["status"] == "optimal":
                result["reason"] = "Budget is below the cheapest otherwise-feasible order"
                result["minimum_required_minor"] = without_budget["accounting"]["total_minor"]
        return result
    if solution.x is None or solution.status not in (0, 1):
        return {**result, "status": "unresolved", "reason": "No verified feasible incumbent was returned"}
    if any(abs(value - round(value)) > 1e-5 for value in solution.x):
        return {**result, "status": "unresolved", "reason": "Solver incumbent failed integrality verification"}
    allocation = [{"offer_id": offers[oi]["id"], "line_id": lines[li]["id"], "packs": round(solution.x[e])}
                  for e, (oi, li) in enumerate(edges) if round(solution.x[e]) > 0]
    try:
        totals = account(brief, snapshot, allocation, as_of)
    except InputError as error:
        return {**result, "status": "unresolved", "reason": f"Independent validation failed: {error}"}
    result.update(status="optimal" if solution.status == 0 else "feasible_not_proven",
                  allocations=allocation, accounting=totals)
    verify_plan(brief, snapshot, result, as_of)
    return result


def frontier(brief, snapshot, as_of, time_limit=3.0):
    validate_brief(brief)
    validate_quotes(snapshot)
    suppliers = {supplier["id"]: supplier for supplier in snapshot["suppliers"]}
    limits = sorted({offer["lead_days"] for offer in snapshot["offers"] if any(
        not exclusion_reasons(offer, suppliers[offer["supplier_id"]], line, brief, as_of)
        for line in brief["lines"])})
    if len(limits) > 20:
        raise InputError("Frontier supports at most 20 distinct delivery limits")
    plans = []
    unresolved = []
    for limit in limits:
        constrained = copy.deepcopy(brief)
        constrained["deadline_days"] = limit
        plan = solve(constrained, snapshot, as_of, time_limit, diagnose=False)
        if plan["status"] == "optimal":
            # The returned allocation is also valid for the user's original deadline.
            plan["brief_sha256"] = digest(brief)
            plan["search_deadline_days"] = limit
            verify_plan(brief, snapshot, plan, as_of)
            point = (plan["accounting"]["total_minor"], plan["accounting"]["lead_days"])
            if not any((p["accounting"]["total_minor"], p["accounting"]["lead_days"]) == point for p in plans):
                plans.append(plan)
        elif plan["status"] != "infeasible":
            unresolved.append(limit)
    nondominated = [plan for plan in plans if not any(
        other["accounting"]["total_minor"] <= plan["accounting"]["total_minor"]
        and other["accounting"]["lead_days"] <= plan["accounting"]["lead_days"]
        and other["accounting"] != plan["accounting"]
        and (other["accounting"]["total_minor"] < plan["accounting"]["total_minor"]
             or other["accounting"]["lead_days"] < plan["accounting"]["lead_days"])
        for other in plans)]
    return {"status": "complete" if not unresolved else "partial", "unresolved_delivery_limits": unresolved,
            "plans": sorted(nondominated, key=lambda p: p["accounting"]["lead_days"])}
