from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .constants import UPLOAD_MARKER_HEADERS
from .models import UploadMarkerResult
from .run_csv_repository import RunCsvRepository


class UploadMarkerWriter:
    def __init__(self, repo: RunCsvRepository) -> None:
        self.repo = repo

    def mark_uploaded_rows(
        self,
        *,
        final_csv_path: Path,
        uploaded_levels: dict[int, int],
        status_by_word_id: dict[int, str],
        upload_batch_id: str,
        uploaded_at: str | None = None,
    ) -> UploadMarkerResult:
        if not status_by_word_id:
            return UploadMarkerResult(marker_path=final_csv_path, used_companion_file=False, marked_rows=0)

        uploaded_at = uploaded_at or datetime.now(timezone.utc).isoformat()
        try:
            return self._mark_in_place(
                final_csv_path=final_csv_path,
                uploaded_levels=uploaded_levels,
                status_by_word_id=status_by_word_id,
                upload_batch_id=upload_batch_id,
                uploaded_at=uploaded_at,
            )
        except PermissionError:
            return self._write_companion(
                final_csv_path=final_csv_path,
                uploaded_levels=uploaded_levels,
                status_by_word_id=status_by_word_id,
                upload_batch_id=upload_batch_id,
                uploaded_at=uploaded_at,
            )

    def _mark_in_place(
        self,
        *,
        final_csv_path: Path,
        uploaded_levels: dict[int, int],
        status_by_word_id: dict[int, str],
        upload_batch_id: str,
        uploaded_at: str,
    ) -> UploadMarkerResult:
        table = self.repo.read_table(final_csv_path)
        if "word_id" not in table.headers:
            raise ValueError(f"CSV {final_csv_path} missing word_id")

        headers = table.headers + [h for h in UPLOAD_MARKER_HEADERS if h not in table.headers]
        rows: list[list[str]] = []
        marked = 0

        for rec in table.records:
            row = dict(zip(table.headers, rec.values))
            try:
                word_id = int(row.get("word_id", ""))
            except Exception:
                word_id = None
            status = status_by_word_id.get(word_id) if word_id is not None else None
            if status is not None:
                row["uploaded_at"] = uploaded_at
                row["uploaded_level"] = str(uploaded_levels.get(word_id, ""))
                row["upload_status"] = status
                row["upload_batch_id"] = upload_batch_id
                marked += 1
            else:
                for k in UPLOAD_MARKER_HEADERS:
                    row.setdefault(k, "")
            rows.append([row.get(h, "") for h in headers])

        self.repo.write_table_atomic(final_csv_path, headers, rows)
        return UploadMarkerResult(marker_path=final_csv_path, used_companion_file=False, marked_rows=marked)

    def _write_companion(
        self,
        *,
        final_csv_path: Path,
        uploaded_levels: dict[int, int],
        status_by_word_id: dict[int, str],
        upload_batch_id: str,
        uploaded_at: str,
    ) -> UploadMarkerResult:
        companion = final_csv_path.with_name(f"{final_csv_path.name}.upload_markers.csv")
        headers = ["word_id", *UPLOAD_MARKER_HEADERS]
        rows = []
        for word_id, status in sorted(status_by_word_id.items()):
            rows.append([
                str(word_id),
                uploaded_at,
                str(uploaded_levels.get(word_id, "")),
                status,
                upload_batch_id,
            ])
        self.repo.write_rows(companion, headers, rows)
        return UploadMarkerResult(marker_path=companion, used_companion_file=True, marked_rows=len(rows))
