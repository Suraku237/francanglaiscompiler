import unittest
from unittest.mock import Mock, patch

from tools.benchmark_collector import measure, nearest_rank_p95, synthetic_entries


class BenchmarkMethodTests(unittest.TestCase):
    def test_nearest_rank_uses_the_nineteenth_of_twenty_samples(self) -> None:
        self.assertEqual(nearest_rank_p95(list(range(20, 0, -1))), 19)
        self.assertEqual(nearest_rank_p95([3, 1, 2]), 3)
        self.assertEqual(nearest_rank_p95([4.5]), 4.5)

    def test_invalid_samples_are_rejected(self) -> None:
        for samples in ([], [-1.0], [float("nan")], [float("inf")]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                nearest_rank_p95(samples)

    def test_warmup_is_excluded_and_real_handlers_are_called(self) -> None:
        refresh, flush = Mock(), Mock()
        timestamps = [0, 1_000_000, 2_000_000, 5_000_000]
        with patch("tools.benchmark_collector.time.perf_counter_ns", side_effect=timestamps):
            report = measure(refresh, flush, 2)
        self.assertEqual(refresh.call_count, 3)
        self.assertEqual(flush.call_count, 3)
        self.assertEqual(report["samples_ms"], [1.0, 3.0])
        self.assertEqual(report["p95_ms"], 3.0)
        self.assertEqual(report["warmups"], 1)

    def test_fixture_has_exact_size_and_no_fieldwork_claims(self) -> None:
        entries = synthetic_entries(1000, 500)
        self.assertEqual(len(entries), 1000)
        self.assertTrue(all(len(entry["text"]) == 500 for entry in entries))
        self.assertEqual(len({entry["id"] for entry in entries}), 1000)
        self.assertTrue(all(entry["review_status"] == "unreviewed" for entry in entries))
        self.assertTrue(all(entry["language"] == "unspecified" for entry in entries))
        self.assertTrue(all(not entry["audio_filename"] for entry in entries))

    def test_unbounded_or_empty_runs_and_fixtures_are_rejected(self) -> None:
        for runs in (0, 101):
            with self.subTest(runs=runs), self.assertRaises(ValueError):
                measure(Mock(), Mock(), runs)
        for rows, characters in ((0, 500), (10001, 500), (10, 1), (10, 4001)):
            with self.subTest(rows=rows, characters=characters), self.assertRaises(ValueError):
                synthetic_entries(rows, characters)


if __name__ == "__main__":
    unittest.main()
