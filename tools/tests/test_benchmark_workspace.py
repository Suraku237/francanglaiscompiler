import unittest
from unittest.mock import patch

from tools.benchmark_workspace import run_benchmark


class WorkspaceBenchmarkTests(unittest.TestCase):
    def test_small_real_fixture_verifies_response_shapes_and_produces_measurements(self):
        report = run_benchmark(rows=3, text_characters=80, runs=1, limit_ms=60000)
        self.assertTrue(report["passed_on_this_machine"])
        self.assertEqual(report["fixture"], {"rows": 3, "text_characters": 80, "synthetic": True, "accounts": 1})
        self.assertEqual(set(report["measurements"]), {"list_all", "search_one", "create_verified_backup"})
        for item in report["measurements"].values():
            self.assertEqual((item["runs"], item["warmups"]), (1, 1))
            self.assertEqual(len(item["samples_ms"]), 1)
            self.assertGreaterEqual(item["p95_ms"], 0)

    def test_budget_uses_p95_and_accepts_the_exact_boundary(self):
        for p95, expected in ((1000, True), (1000.01, False)):
            with self.subTest(p95=p95), patch("tools.benchmark_workspace.measure", return_value={"p95_ms": p95, "mean_ms": 1}):
                report = run_benchmark(rows=1, text_characters=80, runs=1)
                self.assertIs(report["passed_on_this_machine"], expected)

    def test_invalid_bounds_fail_before_creating_a_workspace(self):
        for options in ({"runs": 0}, {"runs": 61}, {"rows": 0}, {"limit_ms": float("nan")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                run_benchmark(**options)
