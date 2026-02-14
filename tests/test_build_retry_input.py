import json
import tempfile
import unittest
from pathlib import Path

from classificator.run_csv_repository import RunCsvRepository
from classificator.tools.build_retry_input import build_retry_input


class BuildRetryInputTest(unittest.TestCase):
    def setUp(self):
        self.repo = RunCsvRepository()

    def test_build_retry_input_selects_failed_word_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            failed = root / "failed.jsonl"
            base = root / "base.csv"
            out = root / "retry.csv"

            rows = [
                {"word_id": 2, "error": "x"},
                {"word_id": 4, "error": "y"},
                {"word_id": 2, "error": "dup"},
                {"word_id": "bad", "error": "bad"},
            ]
            failed.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            self.repo.write_rows(
                base,
                ["word_id", "word", "type"],
                [
                    ["1", "unu", "N"],
                    ["2", "doi", "N"],
                    ["3", "trei", "N"],
                    ["4", "patru", "N"],
                ],
            )

            count = build_retry_input(failed_jsonl=failed, base_csv=base, output_csv=out, repo=self.repo)
            self.assertEqual(count, 2)

            table = self.repo.read_table(out)
            self.assertEqual(table.headers, ["word_id", "word", "type"])
            ids = [int(rec.values[0]) for rec in table.records]
            self.assertEqual(ids, [2, 4])


if __name__ == "__main__":
    unittest.main()
