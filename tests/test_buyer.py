import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent import execute_decision, parse_decision, run_chat
from catalog import load_products
from cli import main
from evaluation import evaluate
from service import BuyerService


class BuyerTests(unittest.TestCase):
    def setUp(self):
        self.service = BuyerService(demo=True)

    def test_budget_and_dimensions(self):
        results = self.service.search("浅粉色花束", 50, color="浅粉色", form="花束",
                                      currency="GBP", max_price=10, max_height_cm=40)
        self.assertTrue(results)
        for item in results:
            self.assertLessEqual(item["price"], 10)
            self.assertLessEqual(item["details"]["height_cm"], 40)
            self.assertEqual(item["details"]["color"], "浅粉色")
            self.assertEqual(item["details"]["form"], "花束")

    def test_unknown_dimensions_fail_closed(self):
        results = self.service.search("花环", 200, max_height_cm=100)
        self.assertTrue(all(item["details"]["height_cm"] is not None for item in results))
        self.assertFalse(self.service.search("花环", form="花环", max_height_cm=100))

    def test_historical_prices_are_not_unit_quotes(self):
        self.service.products = [{"parent_asin": "A", "title": "pink flower", "price": 1,
                                  "currency": "USD", "details": {}}]
        self.assertFalse(self.service.search("flower", currency="USD", max_price=10))
        self.assertIn("Historical", self.service.details("A")["price_note"])

    def test_invalid_inputs(self):
        for filters in ({"max_price": 10}, {"max_price": float("nan"), "currency": "GBP"},
                        {"max_height_cm": -1}):
            with self.assertRaises(ValueError):
                self.service.search("flower", **filters)
        for query in ("", " "):
            with self.assertRaises(ValueError):
                self.service.search(query)
        with self.assertRaises(ValueError):
            self.service.search("flower", 0)

    def test_no_match_and_unknown_id(self):
        self.assertFalse(self.service.search("火星矿石"))
        self.assertFalse(self.service.details("MISSING")["found"])

    def test_lookup_and_id_grounding(self):
        decision = {"action": "get_product_details", "arguments": {"product_id": "P0001"}}
        kind, result = execute_decision(decision, "查 P0001 的颜色", self.service)
        self.assertEqual(kind, "tool_result")
        self.assertTrue(result["found"])
        for question in ("查那款的颜色", "查 XP0001 的颜色"):
            with self.assertRaises(ValueError):
                execute_decision(decision, question, self.service)

    def test_malformed_tool_calls(self):
        cases = [[], {"action": []}, {"action": "shell"},
                 {"action": "clarify", "message": ""},
                 {"action": "search_products", "arguments": {"requirement": "x", "command": "x"}}]
        for decision in cases:
            with self.assertRaises(ValueError):
                execute_decision(decision, service=self.service)
        with self.assertRaises(ValueError):
            parse_decision("[]")
        self.assertEqual(parse_decision('```json\n{"action":"clarify","message":"编号？"}\n```')["action"], "clarify")

    def test_catalog_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "products.jsonl"
            for content in ('not json', '{"title":"missing ID"}', '{"id":"A"}\n{"id":"A"}', ''):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_products(path)

    def test_cli_demo_without_ml_dependencies(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["--demo", "details", "P0001"])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["found"])

    def test_evaluation_checks_arguments(self):
        class Stub:
            def generate_answer(self, prompt):
                return '{"action":"get_product_details","arguments":{"product_id":"P0002"}}'
        report = evaluate(Stub(), [{"question": "Compare P0001 and P0002", "answer":
                          {"action": "get_product_details", "arguments": {"product_id": "P0001"}}}])
        self.assertEqual(report["action_accuracy"], 1)
        self.assertEqual(report["exact_arguments_accuracy"], 0)

    def test_clarification_preserves_question(self):
        prompts = []
        class Stub:
            def generate_answer(self, prompt):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return '{"action":"clarify","message":"编号？"}'
                if len(prompts) == 2:
                    return '{"action":"get_product_details","arguments":{"product_id":"P0001"}}'
                return "P0001"
        with patch("builtins.input", side_effect=["查这款的颜色", "P0001", "quit"]), contextlib.redirect_stdout(io.StringIO()):
            run_chat(Stub(), self.service)
        self.assertIn("查这款的颜色", prompts[1])
        self.assertIn("P0001", prompts[2])


if __name__ == "__main__":
    unittest.main()
