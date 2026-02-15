from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..run_csv_repository import RunCsvRepository

_DEFAULT_LEVEL_COLUMNS = ("final_level", "rarity_level", "median_level")
_DECIDED_LABELS = {"1", "2", "3", "unknown_4_5"}


@dataclass(frozen=True)
class ReviewItem:
    word_id: int
    word: str
    type: str
    predicted_level: int
    predicted_confidence: float


@dataclass(frozen=True)
class ReviewLabel:
    word_id: int
    predicted_level: int
    label: str


@dataclass(frozen=True)
class L1ReviewStats:
    reviewed_decided: int
    accepted_level1: int
    precision: float


def run_review_low_confidence(
    *,
    csv_path: Path,
    labels_csv: Path,
    repo: RunCsvRepository,
    level_column: str | None = None,
    confidence_column: str = "confidence",
    only_levels: set[int] | None = None,
    max_items: int = 200,
    include_undecided: bool = False,
) -> None:
    items = load_review_items(
        csv_path=csv_path,
        repo=repo,
        level_column=level_column,
        confidence_column=confidence_column,
        only_levels=only_levels,
    )
    latest = load_latest_review_labels(labels_csv)
    queue = build_review_queue(items, latest, include_undecided=include_undecided)
    if max_items > 0:
        queue = queue[:max_items]

    print(f"input_csv={csv_path}")
    print(f"labels_csv={labels_csv}")
    print(f"queue_size={len(queue)} include_undecided={str(include_undecided).lower()} max_items={max_items}")
    print("labels: 1 | 2 | 3 | u=unknown(4/5) | d=undecided | s=skip | q=quit")

    if not queue:
        _print_l1_summary(latest)
        return

    session_labeled = 0
    for idx, item in enumerate(queue, start=1):
        print(
            f"[{idx}/{len(queue)}] word_id={item.word_id} word='{item.word}' type={item.type} "
            f"pred_level={item.predicted_level} confidence={item.predicted_confidence:.4f}"
        )
        while True:
            raw = input("label> ").strip().lower()
            mapped = _map_input_to_label(raw)
            if mapped is None:
                print("Invalid input. Use: 1,2,3,u,d,s,q")
                continue
            if mapped == "quit":
                latest = load_latest_review_labels(labels_csv)
                print(f"session_labeled={session_labeled}")
                _print_l1_summary(latest)
                return
            if mapped == "skip":
                break
            append_review_label(
                labels_csv=labels_csv,
                run_csv=csv_path,
                item=item,
                label=mapped,
            )
            latest[item.word_id] = ReviewLabel(
                word_id=item.word_id,
                predicted_level=item.predicted_level,
                label=mapped,
            )
            session_labeled += 1
            break

    print(f"session_labeled={session_labeled}")
    _print_l1_summary(latest)


def run_l1_review_check(
    *,
    labels_csv: Path,
    min_precision: float | None = None,
    min_reviewed: int | None = None,
) -> L1ReviewStats:
    latest = load_latest_review_labels(labels_csv)
    stats = compute_l1_review_stats(latest)
    print(f"labels_csv={labels_csv}")
    print(f"l1_reviewed_decided={stats.reviewed_decided}")
    print(f"l1_accepted={stats.accepted_level1}")
    print(f"l1_precision={stats.precision:.4f}")

    failures: list[str] = []
    if min_reviewed is not None and stats.reviewed_decided < min_reviewed:
        failures.append(f"l1_reviewed_decided {stats.reviewed_decided} < min {min_reviewed}")
    if min_precision is not None and stats.precision < min_precision:
        failures.append(f"l1_precision {stats.precision:.4f} < min {min_precision:.4f}")

    if failures:
        print("l1_review_gate=FAIL")
        for item in failures:
            print(f"- {item}")
        raise SystemExit(1)

    print("l1_review_gate=PASS")
    return stats


def load_review_items(
    *,
    csv_path: Path,
    repo: RunCsvRepository,
    level_column: str | None = None,
    confidence_column: str = "confidence",
    only_levels: set[int] | None = None,
) -> list[ReviewItem]:
    table = repo.read_table(csv_path)
    level_col = _resolve_level_column(table.headers, level_column)
    idx_word_id = _require_col(table.headers, "word_id")
    idx_word = _require_col(table.headers, "word")
    idx_type = table.headers.index("type") if "type" in table.headers else None
    idx_level = table.headers.index(level_col)
    idx_conf = table.headers.index(confidence_column) if confidence_column in table.headers else None

    items: list[ReviewItem] = []
    for rec in table.records:
        vals = rec.values
        if len(vals) == 1 and vals[0] == "":
            continue
        word_id = _parse_int(vals[idx_word_id], f"word_id at row {rec.line_number} in {csv_path}")
        word = vals[idx_word].strip()
        wtype = vals[idx_type].strip() if idx_type is not None else ""
        level = _parse_int(vals[idx_level], f"{level_col} at row {rec.line_number} in {csv_path}")
        if level < 1 or level > 5:
            raise ValueError(f"Invalid {level_col} {level} at row {rec.line_number} in {csv_path}")
        if only_levels is not None and level not in only_levels:
            continue
        confidence = 1.0
        if idx_conf is not None:
            confidence = _parse_float(vals[idx_conf], f"{confidence_column} at row {rec.line_number} in {csv_path}")
            if confidence < 0.0 or confidence > 1.0:
                raise ValueError(
                    f"Invalid {confidence_column} {confidence} at row {rec.line_number} in {csv_path}"
                )
        items.append(
            ReviewItem(
                word_id=word_id,
                word=word,
                type=wtype,
                predicted_level=level,
                predicted_confidence=confidence,
            )
        )
    items.sort(key=lambda i: (i.predicted_confidence, i.word_id))
    return items


def parse_only_levels(raw: str | None) -> set[int] | None:
    if raw is None or raw.strip() == "":
        return None
    out: set[int] = set()
    for part in raw.split(","):
        t = part.strip()
        if not t:
            continue
        try:
            level = int(t)
        except Exception as exc:
            raise ValueError(f"Invalid level '{t}' in --only-levels") from exc
        if level < 1 or level > 5:
            raise ValueError(f"Invalid level '{level}' in --only-levels (allowed 1..5)")
        out.add(level)
    if not out:
        return None
    return out


def load_latest_review_labels(labels_csv: Path) -> dict[int, ReviewLabel]:
    if not labels_csv.exists():
        return {}
    latest: dict[int, ReviewLabel] = {}
    with labels_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            word_id = _parse_int(row.get("word_id", ""), f"word_id in {labels_csv}")
            predicted_level = _parse_int(row.get("predicted_level", ""), f"predicted_level in {labels_csv}")
            label = (row.get("label", "") or "").strip()
            latest[word_id] = ReviewLabel(word_id=word_id, predicted_level=predicted_level, label=label)
    return latest


def build_review_queue(
    items: list[ReviewItem],
    latest_labels: dict[int, ReviewLabel],
    *,
    include_undecided: bool,
) -> list[ReviewItem]:
    out: list[ReviewItem] = []
    for item in items:
        label = latest_labels.get(item.word_id)
        if label is None:
            out.append(item)
            continue
        if include_undecided and label.label == "undecided":
            out.append(item)
    return out


def append_review_label(*, labels_csv: Path, run_csv: Path, item: ReviewItem, label: str) -> None:
    labels_csv.parent.mkdir(parents=True, exist_ok=True)
    exists = labels_csv.exists()
    with labels_csv.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        if not exists:
            writer.writerow(
                [
                    "ts_utc",
                    "run_csv",
                    "word_id",
                    "word",
                    "type",
                    "predicted_level",
                    "predicted_confidence",
                    "label",
                ]
            )
        writer.writerow(
            [
                datetime.now(tz=timezone.utc).isoformat(),
                str(run_csv),
                str(item.word_id),
                item.word,
                item.type,
                str(item.predicted_level),
                f"{item.predicted_confidence:.6f}",
                label,
            ]
        )


def compute_l1_review_stats(latest_labels: dict[int, ReviewLabel]) -> L1ReviewStats:
    reviewed = 0
    accepted = 0
    for row in latest_labels.values():
        if row.predicted_level != 1:
            continue
        if row.label not in _DECIDED_LABELS:
            continue
        reviewed += 1
        if row.label == "1":
            accepted += 1
    precision = (accepted / reviewed) if reviewed > 0 else 0.0
    return L1ReviewStats(
        reviewed_decided=reviewed,
        accepted_level1=accepted,
        precision=precision,
    )


def _print_l1_summary(latest: dict[int, ReviewLabel]) -> None:
    stats = compute_l1_review_stats(latest)
    print(f"l1_reviewed_decided={stats.reviewed_decided}")
    print(f"l1_accepted={stats.accepted_level1}")
    print(f"l1_precision={stats.precision:.4f}")


def _map_input_to_label(raw: str) -> str | None:
    if raw in {"1", "2", "3"}:
        return raw
    if raw in {"u", "unknown"}:
        return "unknown_4_5"
    if raw in {"d", "undecided"}:
        return "undecided"
    if raw in {"s", "skip"}:
        return "skip"
    if raw in {"q", "quit", "exit"}:
        return "quit"
    return None


def _resolve_level_column(headers: list[str], level_column: str | None) -> str:
    if level_column:
        if level_column not in headers:
            raise ValueError(f"CSV missing requested level column '{level_column}'")
        return level_column
    for col in _DEFAULT_LEVEL_COLUMNS:
        if col in headers:
            return col
    raise ValueError("CSV missing level column: final_level/rarity_level/median_level")


def _require_col(headers: list[str], col: str) -> int:
    if col not in headers:
        raise ValueError(f"CSV missing required column '{col}'")
    return headers.index(col)


def _parse_int(raw: str, context: str) -> int:
    try:
        return int(raw)
    except Exception as exc:
        raise ValueError(f"Invalid integer {context}: '{raw}'") from exc


def _parse_float(raw: str, context: str) -> float:
    try:
        return float(raw)
    except Exception as exc:
        raise ValueError(f"Invalid float {context}: '{raw}'") from exc
