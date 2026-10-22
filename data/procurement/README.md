# Normalized procurement scenarios

`brief.json` and `quotes.json` are synthetic fixtures for order planning. They are separate from both the 120-product search demo and the downloaded historical Amazon catalogue. No quote, stock amount, shipping charge or delivery duration is a live supplier statement.

`schema_version` is 1. A brief requires currency, budget, deadline in days, and 1-12 lines. Each line has a unique ID, requested units and exact required attributes. Supported attributes are color, form, material and style; `max_height_cm`, `max_surplus_units` and a brief-wide `max_suppliers` are optional. Unknown fields are rejected. Attribute values are case-insensitive exact text, not semantic guesses.

Each offer belongs to a known supplier and specifies pack price, units per pack, minimum packs, stock in packs, lead time and quote start/end dates. Suppliers supply one flat shipping charge per order in the same currency. A quote may have unknown stock, lead time, height or dates, but it cannot satisfy a requirement that depends on those unknown fields. Unit prices and total prices are not interchangeable.

Supported currencies are GBP, USD and EUR with two decimal places. Amounts become integer minor units with no rounding. The offline replay date for these fixtures is 2026-10-22. Lead times are relative to the planning date, and approval must still meet the original deadline. Free-text descriptions are inert data.

`evaluate_planner.py` generates a separate seeded small-case reference suite; `benchmark_planner.py` generates larger synthetic quote books. Their complete snapshots are retained in `results/`. These fixtures validate software behavior, not shopping preferences or economic performance.
