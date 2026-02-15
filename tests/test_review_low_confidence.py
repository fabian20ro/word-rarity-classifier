import tempfile
import unittest
from pathlib import Path

from classificator.run_csv_repository import RunCsvRepository
from classificator.tools.review_low_confidence import (
    ReviewLabel,
    build_review_queue,
    compute_l1_review_stats,
    load_review_items,
    parse_only_levels,
)


class ReviewLowConfidenceTest(unittest.TestCase):
    def setUp(self):
        self.repo = RunCsvRepository()

    def _write_csv(self, path: Path, headers: list[str], rows: list[list[str]]):
        self.repo.write_rows(path, headers, rows)

    def test_parse_only_levels(self):
        self.assertIsNone(parse_only_levels(None))
        self.assertEqual(parse_only_levels("1,3,5"), {1, 3, 5})
        with self.assertRaises(ValueError):
            parse_only_levels("0")
        with self.assertRaises(ValueError):
            parse_only_levels("x")

    def test_load_items_sorted_by_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "run.csv"
            self._write_csv(
                path,
                ["word_id", "word", "type", "rarity_level", "confidence"],
                [
                    ["10", "cuvant10", "N", "1", "0.9"],
                    ["11", "cuvant11", "N", "1", "0.2"],
                    ["12", "cuvant12", "N", "4", "0.5"],
                ],
            )
            items = load_review_items(csv_path=path, repo=self.repo, only_levels={1})
            self.assertEqual([x.word_id for x in items], [11, 10])

    def test_queue_skips_labeled_unless_undecided_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "run.csv"
            self._write_csv(
                path,
                ["word_id", "word", "type", "rarity_level", "confidence"],
                [
                    ["1", "a", "N", "1", "0.1"],
                    ["2", "b", "N", "1", "0.2"],
                    ["3", "c", "N", "1", "0.3"],
                ],
            )
            items = load_review_items(csv_path=path, repo=self.repo)
            labels = {
                1: ReviewLabel(word_id=1, predicted_level=1, label="1"),
                2: ReviewLabel(word_id=2, predicted_level=1, label="undecided"),
            }
            queue_default = build_review_queue(items, labels, include_undecided=False)
            self.assertEqual([x.word_id for x in queue_default], [3])
            queue_with_undecided = build_review_queue(items, labels, include_undecided=True)
            self.assertEqual([x.word_id for x in queue_with_undecided], [2, 3])

    def test_l1_stats_precision(self):
        labels = {
            1: ReviewLabel(word_id=1, predicted_level=1, label="1"),
            2: ReviewLabel(word_id=2, predicted_level=1, label="2"),
            3: ReviewLabel(word_id=3, predicted_level=1, label="unknown_4_5"),
            4: ReviewLabel(word_id=4, predicted_level=1, label="undecided"),
            5: ReviewLabel(word_id=5, predicted_level=2, label="1"),
        }
        stats = compute_l1_review_stats(labels)
        self.assertEqual(stats.reviewed_decided, 3)
        self.assertEqual(stats.accepted_level1, 1)
        self.assertAlmostEqual(stats.precision, 1 / 3)


if __name__ == "__main__":
    unittest.main()
