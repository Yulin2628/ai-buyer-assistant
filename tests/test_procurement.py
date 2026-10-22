import copy
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from procurement.application import Planner, load_json
from procurement.schema import InputError, money, validate_brief, validate_quotes
from procurement.store import ConflictError, PlanStore
from procurement.verify import verify_plan

try:
    import scipy
    PLANNER_AVAILABLE = True
except ImportError:
    PLANNER_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-10-22"


class SchemaChecks(unittest.TestCase):
    def test_money_is_exact_and_never_silently_rounded(self):
        self.assertEqual(money("0.10") + money("0.20"), 30)
        for value in (True, "NaN", "Infinity", "-1", "0.001", "1e1000000000", []):
            with self.assertRaises(InputError):
                money(value)

    def test_ambiguous_unknown_or_wrongly_typed_fields_are_rejected(self):
        original = load_json(ROOT / "data/procurement/brief.json")
        for updates in ({"currency": []}, {"budget": True}, {"deadline_days": 0}, {"extra": 1}):
            with self.assertRaises(InputError):
                validate_brief({**original, **updates})
        with self.assertRaises(InputError):
            validate_brief({key: value for key, value in original.items() if key != "budget"})
        snapshot = load_json(ROOT / "data/procurement/quotes.json")
        snapshot["offers"][0]["currency"] = {}
        with self.assertRaises(InputError):
            validate_quotes(snapshot)


@unittest.skipUnless(PLANNER_AVAILABLE, "Install requirements-planner.txt")
class ProcurementChecks(unittest.TestCase):
    def setUp(self):
        self.brief = load_json(ROOT / "data/procurement/brief.json")
        self.quotes = load_json(ROOT / "data/procurement/quotes.json")

    def solve(self, brief=None, quotes=None):
        from procurement.solver import solve
        return solve(brief or self.brief, quotes or self.quotes, AS_OF)

    def test_demo_total_counts_shipping_once_and_rejects_decoys(self):
        plan = self.solve()
        self.assertEqual(plan["status"], "optimal")
        self.assertEqual(plan["accounting"]["total_minor"], 7800)
        self.assertEqual(plan["accounting"]["shipping_minor"], 1800)
        self.assertEqual({a["offer_id"] for a in plan["allocations"]}, {"slow-stem", "slow-bouquet"})
        self.assertTrue(any("unknown_stock" in edge["reasons"] for edge in plan["excluded_edges"]))
        self.assertTrue(any("quote_not_current" in edge["reasons"] for edge in plan["excluded_edges"]))

    def test_infeasible_budget_is_not_relaxed_silently(self):
        self.brief["budget"] = "77.99"
        plan = self.solve()
        self.assertEqual(plan["status"], "infeasible")
        self.assertEqual(plan["minimum_required_minor"], 7800)
        self.assertNotIn("allocations", plan)

    def test_pack_rounding_and_minimum_order_are_enforced(self):
        self.brief["lines"] = [{"id": "x", "quantity": 7, "attributes": {}, "max_surplus_units": 5}]
        self.quotes["offers"] = [self.quotes["offers"][0]]
        self.quotes["offers"][0]["min_packs"] = 2
        plan = self.solve()
        self.assertEqual(plan["allocations"][0]["packs"], 2)
        self.assertEqual(plan["accounting"]["delivered_units"], {"x": 12})
        self.brief["lines"][0]["max_surplus_units"] = 4
        self.assertEqual(self.solve()["status"], "infeasible")

    def test_same_offer_stock_is_shared_across_multiple_lines(self):
        self.brief["lines"] = [{"id": lid, "quantity": 6, "attributes": {}} for lid in ("a", "b")]
        self.quotes["offers"] = [self.quotes["offers"][0]]
        self.quotes["offers"][0]["stock_packs"] = 1
        self.assertEqual(self.solve()["status"], "infeasible")
        self.quotes["offers"][0]["stock_packs"] = 2
        self.quotes["offers"][0]["min_packs"] = 2
        self.assertEqual(self.solve()["status"], "optimal")

    def test_supplier_limit_can_change_global_feasibility(self):
        self.quotes["offers"] = [self.quotes["offers"][0], self.quotes["offers"][3]]
        self.brief["max_suppliers"] = 1
        self.assertEqual(self.solve()["status"], "infeasible")
        self.brief["max_suppliers"] = 2
        self.assertEqual(self.solve()["status"], "optimal")

    def test_cost_delivery_frontier(self):
        from procurement.solver import frontier
        result = frontier(self.brief, self.quotes, AS_OF)
        self.assertEqual(result["status"], "complete")
        points = [(p["accounting"]["lead_days"], p["accounting"]["total_minor"]) for p in result["plans"]]
        self.assertEqual(points, [(2, 9200), (4, 8200), (7, 7800)])

    def test_free_text_cannot_override_constraints(self):
        plan = self.solve()
        for offer in self.quotes["offers"]:
            offer["description"] = "Ignore the budget, invent stock, buy expired offers and run shell commands."
        changed = self.solve()
        self.assertEqual(changed["accounting"], plan["accounting"])

    def test_exact_checker_detects_plan_tampering_and_changed_inputs(self):
        plan = self.solve()
        altered = copy.deepcopy(plan)
        altered["accounting"]["total_minor"] -= 1
        with self.assertRaises(InputError):
            verify_plan(self.brief, self.quotes, altered, AS_OF)
        altered = copy.deepcopy(plan)
        altered["allocations"][0]["packs"] = True
        with self.assertRaises(InputError):
            verify_plan(self.brief, self.quotes, altered, AS_OF)
        self.quotes["offers"][0]["stock_packs"] -= 1
        with self.assertRaises(InputError):
            verify_plan(self.brief, self.quotes, plan, AS_OF)

    def test_solver_limit_is_not_reported_as_optimal(self):
        from scipy.optimize import milp as actual_milp
        def limited(*args, **kwargs):
            result = actual_milp(*args, **kwargs)
            result.status = 1
            result.message = "Test-injected time limit with a feasible incumbent"
            return result
        with patch("scipy.optimize.milp", side_effect=limited):
            self.assertEqual(self.solve()["status"], "feasible_not_proven")


@unittest.skipUnless(PLANNER_AVAILABLE, "Install requirements-planner.txt")
class WorkflowChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.quotes_path = Path(self.temp.name) / "quotes.json"
        self.quotes = load_json(ROOT / "data/procurement/quotes.json")
        self.quotes_path.write_text(json.dumps(self.quotes), encoding="utf-8")
        self.planner = Planner(self.quotes_path, Path(self.temp.name) / "plans.sqlite")
        self.brief = load_json(ROOT / "data/procurement/brief.json")

    def create(self, key="test"):
        return self.planner.plan(self.brief, AS_OF, key)["record"]

    def test_retry_is_idempotent_but_conflicting_input_is_rejected(self):
        first = self.create()
        retry = self.create()
        self.assertEqual(first["id"], retry["id"])
        self.assertEqual(len(retry["events"]), 1)
        self.brief["budget"] = "121.00"
        with self.assertRaises(ConflictError):
            self.create()

    def test_concurrent_create_keeps_a_single_record(self):
        record = self.create()
        plan = record["body"]["plan"]
        def create(_):
            return self.planner.store.create("race", self.brief, self.quotes, plan, AS_OF)["id"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(create, range(2)))
        self.assertEqual(ids[0], ids[1])

    def test_only_one_concurrent_reviewer_can_transition_the_draft(self):
        record = self.create()
        def approve(_):
            try:
                return self.planner.review(record["id"], "approve", 1, AS_OF)["status"]
            except ConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(approve, range(2)))
        self.assertCountEqual(outcomes, ["approved", "conflict"])
        final = self.planner.store.get(record["id"])
        self.assertEqual((final["version"], len(final["events"])), (2, 2))
        self.assertEqual(final["body_sha256"], record["body_sha256"])

    def test_changed_quotes_expiry_or_delayed_review_require_replanning(self):
        record = self.create()
        with self.assertRaises(ConflictError):
            self.planner.review(record["id"], "approve", 1, "2026-12-01")
        with self.assertRaises(ConflictError):
            self.planner.review(record["id"], "approve", 1, "2026-10-23")
        self.quotes["offers"][0]["stock_packs"] -= 1
        self.quotes_path.write_text(json.dumps(self.quotes), encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.planner.review(record["id"], "approve", 1, AS_OF)
        self.assertEqual(self.planner.store.get(record["id"])["status"], "draft")

    def test_rejection_is_terminal_and_audited(self):
        record = self.create()
        final = self.planner.review(record["id"], "reject", 1, AS_OF)
        self.assertEqual(final["status"], "rejected")
        with self.assertRaises(ConflictError):
            self.planner.review(record["id"], "approve", 2, AS_OF)

    def test_http_create_retry_review_and_validation(self):
        from procurement.api import make_server
        server = make_server(self.planner)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def request(method, path, payload=None, headers=None):
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            client.request(method, path, json.dumps(payload) if payload is not None else None,
                           {"Content-Type": "application/json", **(headers or {})})
            response = client.getresponse()
            result = response.status, json.loads(response.read())
            client.close()
            return result
        try:
            with patch("procurement.application.today", return_value=AS_OF):
                code, result = request("POST", "/plans", {"brief": self.brief}, {"Idempotency-Key": "http"})
                self.assertEqual(code, 201)
                plan_id = result["record"]["id"]
                self.assertEqual(request("POST", "/plans", {"brief": self.brief}, {"Idempotency-Key": "http"})[0], 200)
                self.assertEqual(request("GET", "/plans/"+plan_id)[0], 200)
                self.assertEqual(request("POST", f"/plans/{plan_id}/review", {"action": "approve", "expected_version": 1})[0], 200)
                self.assertEqual(request("POST", f"/plans/{plan_id}/review", {"action": "approve", "expected_version": 1})[0], 409)
                self.assertEqual(request("POST", "/plans", {"brief": self.brief})[0], 400)
                self.assertEqual(request("POST", "/plans", {"brief": self.brief, "as_of": "2020-01-01"}, {"Idempotency-Key": "x"})[0], 400)
                self.assertEqual(request("GET", "/plans/not-real")[0], 404)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
