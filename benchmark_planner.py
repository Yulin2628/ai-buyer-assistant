"""Planning latency on seeded synthetic quote books of increasing size."""
import argparse
import json
from pathlib import Path
import platform
import random
import statistics
import time

from procurement.schema import digest
from procurement.solver import solve


def scenario(offer_count, line_count, supplier_count):
    rng = random.Random(2000 + offer_count)
    suppliers = [{"id": f"S{i}", "currency": "GBP", "shipping": f'{rng.randint(200, 2000)/100:.2f}'}
                 for i in range(supplier_count)]
    offers = [{"id": f"O{i:04}", "supplier_id": f"S{i%supplier_count}", "product_id": f"SKU{i%20}",
               "attributes": {"color": "pink" if i % 2 == 0 else "white", "form": "stem"},
               "currency": "GBP", "pack_price": f'{rng.randint(100, 1200)/100:.2f}',
               "pack_size": rng.choice([3, 6, 12]), "min_packs": rng.randint(1, 3),
               "stock_packs": rng.randint(4, 20), "lead_days": rng.randint(1, 7),
               "quoted_on": "2026-10-01", "valid_until": "2026-11-30", "height_cm": 30}
              for i in range(offer_count)]
    brief = {"schema_version": 1, "currency": "GBP", "budget": "10000.00", "deadline_days": 7,
             "lines": [{"id": f"L{i}", "quantity": 24,
                        "attributes": {"color": "pink" if i%2 == 0 else "white", "form": "stem"}}
                       for i in range(line_count)]}
    return {"brief": brief, "quotes": {"schema_version": 1, "source": "synthetic_scaling_fixture",
                                       "suppliers": suppliers, "offers": offers}, "as_of": "2026-10-22"}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/planner_scaling.json"))
    args = parser.parse_args()
    import scipy
    report = {"python": platform.python_version(), "scipy": scipy.__version__,
              "cpu": platform.processor(), "method": "one unmeasured warmup then three repeated full planning calls per case; no HTTP, database or JSON IO in timing",
              "scenarios": []}
    for offers, lines, suppliers in ((50, 3, 5), (200, 6, 12), (500, 12, 20)):
        inputs = scenario(offers, lines, suppliers)
        solve(inputs["brief"], inputs["quotes"], inputs["as_of"], diagnose=False)
        rows = []
        for _ in range(3):
            start = time.perf_counter()
            plan = solve(inputs["brief"], inputs["quotes"], inputs["as_of"], diagnose=False)
            elapsed = (time.perf_counter() - start) * 1000
            rows.append({"planning_ms": elapsed, "plan": plan})
        row = {"offers": offers, "lines": lines, "suppliers": suppliers, "inputs": inputs,
               "input_sha256": digest(inputs), "runs": rows,
               "median_ms": statistics.median(item["planning_ms"] for item in rows)}
        report["scenarios"].append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(offers, lines, row["median_ms"], [item["plan"]["status"] for item in rows], flush=True)


if __name__ == "__main__":
    main()
