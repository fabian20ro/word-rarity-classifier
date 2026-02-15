import json
import tempfile
import unittest
from pathlib import Path

from classificator.distribution import RarityDistribution
from classificator.steps.step5_rebalance import (
    RebalanceRuntime,
    RebalanceWord,
    Step5Logs,
    Step5Options,
    _append_batch_progress,
)
from classificator.transitions import LevelTransition


class Step5ProgressLoggingTest(unittest.TestCase):
    def _mk_logs(self, root: Path) -> Step5Logs:
        return Step5Logs(
            run_log_path=root / "run.jsonl",
            failed_log_path=root / "failed.jsonl",
            switched_words_log_path=root / "switched.jsonl",
            checkpoint_path=root / "checkpoint.jsonl",
            progress_log_path=root / "progress.jsonl",
        )

    def _mk_runtime(self) -> RebalanceRuntime:
        levels = {1: 4, 2: 4, 3: 5}
        return RebalanceRuntime(
            levels_by_id=dict(levels),
            distribution=RarityDistribution.from_levels(list(levels.values())),
            rebalance_rules={},
            processed_word_ids=set(),
        )

    def test_progress_logs_picked_target_words_when_target_is_common(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = self._mk_logs(root)
            runtime = self._mk_runtime()
            options = Step5Options(
                run_slug="rb_test",
                model="m",
                input_csv_path=root / "in.csv",
                output_csv_path=root / "out.csv",
            )
            transition = LevelTransition(from_level=4, to_level=4)
            batch = [
                RebalanceWord(word_id=1, word="a", type="N"),
                RebalanceWord(word_id=2, word="b", type="N"),
            ]
            _append_batch_progress(
                logs=logs,
                options=options,
                transition=transition,
                batch_index=1,
                batch=batch,
                selected_common_word_ids={2},
                common_level=4,
                processed=2,
                eligible_count=10,
                target_assigned=1,
                expected_target_total=5,
                batch_target=1,
                batch_mix="[4:2]",
                runtime=runtime,
            )
            row = json.loads(logs.progress_log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["picked_target_level"], 4)
            self.assertEqual(row["picked_target_word_ids"], [2])
            self.assertEqual(row["picked_target_words"], ["b"])
            self.assertEqual(row["remaining"], 8)

    def test_progress_logs_picked_target_words_when_target_is_rare(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = self._mk_logs(root)
            runtime = self._mk_runtime()
            options = Step5Options(
                run_slug="rb_test",
                model="m",
                input_csv_path=root / "in.csv",
                output_csv_path=root / "out.csv",
            )
            transition = LevelTransition(from_level=2, from_level_upper=3, to_level=3)
            batch = [
                RebalanceWord(word_id=1, word="a", type="N"),
                RebalanceWord(word_id=2, word="b", type="N"),
                RebalanceWord(word_id=3, word="c", type="N"),
            ]
            _append_batch_progress(
                logs=logs,
                options=options,
                transition=transition,
                batch_index=2,
                batch=batch,
                selected_common_word_ids={1, 3},
                common_level=2,
                processed=3,
                eligible_count=20,
                target_assigned=1,
                expected_target_total=6,
                batch_target=1,
                batch_mix="[2:2 3:1]",
                runtime=runtime,
            )
            row = json.loads(logs.progress_log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["picked_target_level"], 3)
            self.assertEqual(row["picked_target_word_ids"], [2])
            self.assertEqual(row["picked_target_words"], ["b"])


if __name__ == "__main__":
    unittest.main()
