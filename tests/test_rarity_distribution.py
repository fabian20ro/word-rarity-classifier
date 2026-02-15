import tempfile
import unittest
from pathlib import Path

from classificator.run_csv_repository import RunCsvRepository
from classificator.tools.rarity_distribution import run_rarity_distribution


class RarityDistributionTest(unittest.TestCase):
    def setUp(self):
        self.repo = RunCsvRepository()

    def _write_csv(self, path: Path, headers: list[str], rows: list[list[str]]):
        self.repo.write_rows(path, headers, rows)

    def test_auto_detects_rarity_level(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "run.csv"
            self._write_csv(
                path,
                ["word_id", "word", "type", "rarity_level"],
                [["1", "om", "N", "1"], ["2", "casă", "N", "2"], ["3", "rar", "A", "5"]],
            )
            result = run_rarity_distribution(csv_path=path, repo=self.repo)
            self.assertEqual(result.level_column, "rarity_level")
            self.assertEqual(result.total_rows, 3)
            self.assertEqual(result.distribution[1], 1)
            self.assertEqual(result.distribution[2], 1)
            self.assertEqual(result.distribution[5], 1)

    def test_can_use_explicit_level_column(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "comparison.csv"
            self._write_csv(
                path,
                ["word_id", "word", "final_level", "median_level"],
                [["1", "om", "1", "2"], ["2", "casă", "3", "2"], ["3", "rar", "5", "4"]],
            )
            result = run_rarity_distribution(csv_path=path, level_column="median_level", repo=self.repo)
            self.assertEqual(result.level_column, "median_level")
            self.assertEqual(result.distribution[2], 2)
            self.assertEqual(result.distribution[4], 1)

    def test_invalid_level_raises(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "bad.csv"
            self._write_csv(
                path,
                ["word_id", "word", "rarity_level"],
                [["1", "om", "0"]],
            )
            with self.assertRaises(ValueError):
                run_rarity_distribution(csv_path=path, repo=self.repo)


if __name__ == "__main__":
    unittest.main()
