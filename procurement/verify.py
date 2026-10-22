"""Recalculate a proposed order with exact integers, independently of solver matrices."""
from collections import Counter

from procurement.schema import (InputError, digest, exclusion_reasons, integer,
                                money, text, iso_date, validate_brief, validate_quotes)


def account(brief, snapshot, allocations, as_of):
    validate_brief(brief)
    validate_quotes(snapshot)
    suppliers = {row["id"]: row for row in snapshot["suppliers"]}
    offers = {row["id"]: row for row in snapshot["offers"]}
    lines = {row["id"]: row for row in brief["lines"]}
    demand = Counter()
    stock = Counter()
    chosen = set()
    seen = set()
    subtotal = 0
    lead = 0
    if not isinstance(allocations, list):
        raise InputError("allocations must be a list")
    for row in allocations:
        if not isinstance(row, dict) or set(row) != {"offer_id", "line_id", "packs"}:
            raise InputError("An allocation needs offer_id, line_id and packs")
        text(row["offer_id"], "offer_id")
        text(row["line_id"], "line_id")
        offer = offers.get(row["offer_id"])
        line = lines.get(row["line_id"])
        if offer is None or line is None:
            raise InputError("An allocation references an unknown offer or line")
        edge = (row["offer_id"], row["line_id"])
        if edge in seen:
            raise InputError("Duplicate allocation edge")
        seen.add(edge)
        packs = integer(row["packs"], "packs", 1, 100_000)
        supplier = suppliers[offer["supplier_id"]]
        reasons = exclusion_reasons(offer, supplier, line, brief, as_of)
        if reasons:
            raise InputError(f"Ineligible offer {offer['id']}: {', '.join(reasons)}")
        demand[line["id"]] += packs * offer["pack_size"]
        stock[offer["id"]] += packs
        subtotal += packs * money(offer["pack_price"])
        lead = max(lead, offer["lead_days"])
        chosen.add(offer["supplier_id"])
    for oid, packs in stock.items():
        if not offers[oid]["min_packs"] <= packs <= offers[oid]["stock_packs"]:
            raise InputError("Order violates aggregate offer stock or minimum order")
    for lid, line in lines.items():
        if not line["quantity"] <= demand[lid] <= line["quantity"] + line.get("max_surplus_units", 0):
            raise InputError("Order violates quantity or maximum surplus")
    if len(chosen) > brief.get("max_suppliers", 100):
        raise InputError("Order uses too many suppliers")
    shipping = sum(money(suppliers[sid]["shipping"]) for sid in chosen)
    total = subtotal + shipping
    if total > money(brief["budget"]):
        raise InputError("Order exceeds the total budget including shipping")
    return {"currency": brief["currency"], "subtotal_minor": subtotal, "shipping_minor": shipping,
            "total_minor": total, "lead_days": lead, "supplier_ids": sorted(chosen),
            "delivered_units": dict(sorted(demand.items())),
            "surplus_units": {lid: demand[lid] - row["quantity"] for lid, row in sorted(lines.items())}}


def verify_plan(brief, snapshot, plan, as_of):
    if plan.get("brief_sha256") != digest(brief) or plan.get("quotes_sha256") != digest(snapshot):
        raise InputError("Plan does not match its input snapshots")
    calculated = account(brief, snapshot, plan.get("allocations"), as_of)
    elapsed = (iso_date(as_of, "as_of") - iso_date(plan.get("as_of"), "plan.as_of")).days
    if elapsed < 0 or elapsed + calculated["lead_days"] > brief["deadline_days"]:
        raise InputError("Approval date would miss the original delivery deadline or precedes planning")
    if plan.get("accounting") != calculated:
        raise InputError("Plan accounting does not match its allocations")
    return calculated
