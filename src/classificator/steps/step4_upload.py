from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..constants import FALLBACK_RARITY_LEVEL, UPLOAD_REPORT_HEADERS
from ..distribution import RarityDistribution
from ..models import UploadMode, WordLevel
from ..run_csv_repository import RunCsvRepository
from ..upload_marker_writer import UploadMarkerWriter
from ..word_store import WordStore


@dataclass(frozen=True)
class Step4Options:
    final_csv_path: Path
    mode: UploadMode
    report_path: Path
    upload_batch_id: str | None


def run_step4(options: Step4Options, *, word_store: WordStore, repo: RunCsvRepository, marker_writer: UploadMarkerWriter) -> None:
    final_levels = repo.load_final_levels(options.final_csv_path)
    db_levels = {wl.word_id: wl for wl in word_store.fetch_all_word_levels()}

    input_dist = RarityDistribution.from_levels(list(final_levels.values()))
    updates, report_rows, status_by_word_id = _build_upload_plan(options.mode, final_levels, db_levels)

    uploaded_dist = RarityDistribution.from_levels(list(updates.values()))
    word_store.update_rarity_levels_chunked(updates)
    repo.write_rows(options.report_path, UPLOAD_REPORT_HEADERS, report_rows)

    marker = marker_writer.mark_uploaded_rows(
        final_csv_path=options.final_csv_path,
        uploaded_levels=updates,
        status_by_word_id=status_by_word_id,
        upload_batch_id=options.upload_batch_id or f"upload_{int(datetime.now(tz=timezone.utc).timestamp() * 1000)}",
        uploaded_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    print(f"Step 4 complete. mode={options.mode.value} updated={len(updates)}")
    print(f"Step 4 input {input_dist.format()}")
    print(f"Step 4 uploaded {uploaded_dist.format()}")
    print(f"Upload report: {options.report_path}")
    print(
        f"Upload markers: {marker.marker_path} (companion={marker.used_companion_file}, marked_rows={marker.marked_rows})"
    )


def _build_upload_plan(
    mode: UploadMode,
    final_levels: dict[int, int],
    db_levels: dict[int, WordLevel],
) -> tuple[dict[int, int], list[list[str]], dict[int, str]]:
    if mode == UploadMode.PARTIAL:
        return _build_partial_plan(final_levels, db_levels)
    return _build_full_fallback_plan(final_levels, db_levels)


def _build_partial_plan(
    final_levels: dict[int, int],
    db_levels: dict[int, WordLevel],
) -> tuple[dict[int, int], list[list[str]], dict[int, str]]:
    updates: dict[int, int] = {}
    report_rows: list[list[str]] = []
    status: dict[int, str] = {}

    for word_id, level in sorted(final_levels.items()):
        existing = db_levels.get(word_id)
        if existing is None:
            report_rows.append([str(word_id), "", "", "missing_db_word"])
            status[word_id] = "missing_db_word"
            continue

        updates[word_id] = level
        report_rows.append([str(word_id), str(existing.rarity_level), str(level), "final_csv"])
        status[word_id] = "uploaded"

    return updates, report_rows, status


def _build_full_fallback_plan(
    final_levels: dict[int, int],
    db_levels: dict[int, WordLevel],
) -> tuple[dict[int, int], list[list[str]], dict[int, str]]:
    updates: dict[int, int] = {}
    report_rows: list[list[str]] = []

    for existing in sorted(db_levels.values(), key=lambda x: x.word_id):
        in_final = existing.word_id in final_levels
        new_level = final_levels.get(existing.word_id, FALLBACK_RARITY_LEVEL)
        source = "final_csv" if in_final else "fallback_4"
        updates[existing.word_id] = new_level
        report_rows.append([str(existing.word_id), str(existing.rarity_level), str(new_level), source])

    status = {
        word_id: ("uploaded" if word_id in db_levels else "missing_db_word")
        for word_id in final_levels.keys()
    }
    return updates, report_rows, status
