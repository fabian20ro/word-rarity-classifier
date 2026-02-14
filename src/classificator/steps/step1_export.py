from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..constants import BASE_CSV_HEADERS
from ..run_csv_repository import RunCsvRepository
from ..word_store import WordStore


@dataclass(frozen=True)
class Step1Options:
    output_csv_path: Path


def run_step1(options: Step1Options, *, word_store: WordStore, repo: RunCsvRepository) -> Path:
    words = sorted(word_store.fetch_all_words(), key=lambda w: w.word_id)
    rows = [[str(w.word_id), w.word, w.type] for w in words]
    repo.write_rows(options.output_csv_path, BASE_CSV_HEADERS, rows)
    print(f"Step 1 complete. Exported {len(words)} words to {options.output_csv_path}")
    return options.output_csv_path
