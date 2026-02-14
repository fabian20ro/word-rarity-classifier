from __future__ import annotations

import csv
from pathlib import Path

from .constants import BASE_CSV_HEADERS, RUN_CSV_HEADERS
from .csv_codec import CsvCodec, CsvFormatError, CsvTable
from .models import BaseWordRow, RunBaseline, RunCsvRow
from .support import required_columns


class RunCsvRepository:
    def __init__(self, codec: CsvCodec | None = None) -> None:
        self.csv = codec or CsvCodec()

    def load_base_rows(self, path: Path) -> list[BaseWordRow]:
        table = self.csv.read_table(path)
        required_columns(table.headers, BASE_CSV_HEADERS, f"CSV {path}")
        out: list[BaseWordRow] = []
        for rec in table.records:
            row = dict(zip(table.headers, rec.values))
            out.append(
                BaseWordRow(
                    word_id=self._parse_int(path, rec.line_number, row, "word_id"),
                    word=self._require_non_blank(path, rec.line_number, row, "word"),
                    type=self._require_non_blank(path, rec.line_number, row, "type"),
                )
            )
        return sorted(out, key=lambda r: r.word_id)

    def load_run_rows(self, path: Path) -> list[RunCsvRow]:
        if not path.exists():
            return []
        table = self.csv.read_table(path)
        required_columns(table.headers, RUN_CSV_HEADERS, f"CSV {path}")

        by_id: dict[int, RunCsvRow] = {}
        for rec in table.records:
            row = dict(zip(table.headers, rec.values))
            rarity = self._parse_int(path, rec.line_number, row, "rarity_level")
            conf = self._parse_float(path, rec.line_number, row, "confidence")
            if rarity < 1 or rarity > 5:
                raise CsvFormatError(f"rarity_level out of range at {path}:{rec.line_number}")
            if conf < 0.0 or conf > 1.0:
                raise CsvFormatError(f"confidence out of range at {path}:{rec.line_number}")

            parsed = RunCsvRow(
                word_id=self._parse_int(path, rec.line_number, row, "word_id"),
                word=self._require_non_blank(path, rec.line_number, row, "word"),
                type=self._require_non_blank(path, rec.line_number, row, "type"),
                rarity_level=rarity,
                tag=row.get("tag", ""),
                confidence=conf,
                scored_at=row.get("scored_at", ""),
                model=row.get("model", ""),
                run_slug=row.get("run_slug", ""),
            )
            by_id[parsed.word_id] = parsed

        return sorted(by_id.values(), key=lambda r: r.word_id)

    def append_run_rows(self, path: Path, rows: list[RunCsvRow]) -> None:
        if not rows:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()
        headers = self._resolve_append_headers(path) if file_exists else RUN_CSV_HEADERS

        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
            if not file_exists:
                writer.writerow(headers)
            for row in rows:
                writer.writerow(self._serialize_for_headers(row, headers))

    def compute_baseline(self, rows: list[RunCsvRow]) -> RunBaseline:
        if not rows:
            return RunBaseline(count=0, min_id=None, max_id=None)
        ids = [r.word_id for r in rows]
        return RunBaseline(count=len(rows), min_id=min(ids), max_id=max(ids))

    def merge_and_rewrite_atomic(self, path: Path, in_memory_rows: list[RunCsvRow], baseline: RunBaseline) -> None:
        merged = {r.word_id: r for r in self.load_run_rows(path)}
        for row in in_memory_rows:
            merged[row.word_id] = row
        merged_rows = sorted(merged.values(), key=lambda r: r.word_id)
        self._assert_not_shrunk(path, merged_rows, baseline)
        self.rewrite_run_rows_atomic(path, merged_rows)

    def rewrite_run_rows_atomic(self, path: Path, rows: list[RunCsvRow]) -> None:
        body = [self._serialize_for_headers(r, RUN_CSV_HEADERS) for r in sorted(rows, key=lambda r: r.word_id)]
        self.csv.write_table_atomic(path, RUN_CSV_HEADERS, body)

    def load_final_levels(self, path: Path) -> dict[int, int]:
        table = self.csv.read_table(path)
        if "word_id" not in table.headers:
            raise ValueError(f"CSV {path} missing required column 'word_id'")

        if "final_level" in table.headers:
            level_col = "final_level"
        elif "rarity_level" in table.headers:
            level_col = "rarity_level"
        elif "median_level" in table.headers:
            level_col = "median_level"
        else:
            raise ValueError("CSV must contain one of: final_level, rarity_level, median_level")

        out: dict[int, int] = {}
        for rec in table.records:
            row = dict(zip(table.headers, rec.values))
            word_id = self._parse_int(path, rec.line_number, row, "word_id")
            level = self._parse_int(path, rec.line_number, row, level_col)
            if level < 1 or level > 5:
                raise CsvFormatError(f"{level_col} out of range at {path}:{rec.line_number}")
            out[word_id] = level
        return out

    def write_rows(self, path: Path, headers: list[str], rows: list[list[str]]) -> None:
        self.csv.write_table(path, headers, rows)

    def read_table(self, path: Path) -> CsvTable:
        return self.csv.read_table(path)

    def write_table_atomic(self, path: Path, headers: list[str], rows: list[list[str]]) -> None:
        self.csv.write_table_atomic(path, headers, rows)

    def _serialize_for_headers(self, row: RunCsvRow, headers: list[str]) -> list[str]:
        base = {
            "word_id": str(row.word_id),
            "word": row.word,
            "type": row.type,
            "rarity_level": str(row.rarity_level),
            "tag": row.tag,
            "confidence": f"{row.confidence}",
            "scored_at": row.scored_at,
            "model": row.model,
            "run_slug": row.run_slug,
        }
        return [base.get(h, "") for h in headers]

    def _resolve_append_headers(self, path: Path) -> list[str]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            headers = next(reader, None)
        if not headers:
            return RUN_CSV_HEADERS
        required_columns([str(x) for x in headers], RUN_CSV_HEADERS, f"CSV {path}")
        return [str(x) for x in headers]

    def _assert_not_shrunk(self, path: Path, merged_rows: list[RunCsvRow], baseline: RunBaseline) -> None:
        merged_count = len(merged_rows)
        if merged_count < baseline.count:
            raise RuntimeError(
                f"Guarded rewrite aborted for {path}: mergedCount={merged_count} < baseline={baseline.count}"
            )
        first_id = merged_rows[0].word_id if merged_rows else None
        last_id = merged_rows[-1].word_id if merged_rows else None
        if baseline.min_id is not None and first_id is not None and first_id > baseline.min_id:
            raise RuntimeError(
                f"Guarded rewrite aborted for {path}: merged minId {first_id} > baseline {baseline.min_id}"
            )
        if baseline.max_id is not None and last_id is not None and last_id < baseline.max_id:
            raise RuntimeError(
                f"Guarded rewrite aborted for {path}: merged maxId {last_id} < baseline {baseline.max_id}"
            )

    def _parse_int(self, path: Path, line: int, row: dict[str, str], key: str) -> int:
        raw = row.get(key, "")
        try:
            return int(raw)
        except Exception as exc:
            raise CsvFormatError(f"Invalid {key} at {path}:{line}") from exc

    def _parse_float(self, path: Path, line: int, row: dict[str, str], key: str) -> float:
        raw = row.get(key, "")
        try:
            return float(raw)
        except Exception as exc:
            raise CsvFormatError(f"Invalid {key} at {path}:{line}") from exc

    def _require_non_blank(self, path: Path, line: int, row: dict[str, str], key: str) -> str:
        val = row.get(key, "")
        if not val.strip():
            raise CsvFormatError(f"Blank {key} at {path}:{line}")
        return val
