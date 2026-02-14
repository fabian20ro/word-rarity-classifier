from __future__ import annotations

import json
from pathlib import Path

from ..run_csv_repository import RunCsvRepository


def build_retry_input(*, failed_jsonl: Path, base_csv: Path, output_csv: Path, repo: RunCsvRepository) -> int:
    if not failed_jsonl.exists():
        raise FileNotFoundError(f"Failed JSONL not found: {failed_jsonl}")
    if not base_csv.exists():
        raise FileNotFoundError(f"Base CSV not found: {base_csv}")

    wanted_ids: set[int] = set()
    with failed_jsonl.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                node = json.loads(line)
            except Exception:
                continue
            word_id = node.get("word_id")
            try:
                wanted_ids.add(int(word_id))
            except Exception:
                continue

    table = repo.read_table(base_csv)
    if not table.records:
        repo.write_rows(output_csv, table.headers, [])
        return 0

    if "word_id" not in table.headers:
        raise ValueError(f"Base CSV must contain word_id: {base_csv}")

    idx = table.headers.index("word_id")
    rows = []
    for rec in table.records:
        try:
            word_id = int(rec.values[idx])
        except Exception:
            continue
        if word_id in wanted_ids:
            rows.append(rec.values)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    repo.write_rows(output_csv, table.headers, rows)
    return len(rows)
