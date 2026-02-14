from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..constants import (
    COMPARISON_CSV_HEADERS,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_OUTLIER_THRESHOLD,
    FALLBACK_RARITY_LEVEL,
    OUTLIERS_CSV_HEADERS,
)
from ..distribution import RarityDistribution
from ..models import BaseWordRow, RunCsvRow, Step3MergeStrategy
from ..run_csv_repository import RunCsvRepository
from ..support import median


@dataclass(frozen=True)
class Step3Options:
    run_a_csv_path: Path
    run_b_csv_path: Path
    run_c_csv_path: Path | None
    output_csv_path: Path
    outliers_csv_path: Path
    base_csv_path: Path
    outlier_threshold: int = DEFAULT_OUTLIER_THRESHOLD
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    merge_strategy: Step3MergeStrategy = Step3MergeStrategy.MEDIAN


def run_step3(options: Step3Options, *, repo: RunCsvRepository) -> None:
    base_rows = repo.load_base_rows(options.base_csv_path)
    run_a = {r.word_id: r for r in repo.load_run_rows(options.run_a_csv_path)}
    run_b = {r.word_id: r for r in repo.load_run_rows(options.run_b_csv_path)}
    run_c = {r.word_id: r for r in repo.load_run_rows(options.run_c_csv_path)} if options.run_c_csv_path else {}

    comparison_rows: list[list[str]] = []
    outlier_rows: list[list[str]] = []
    dist = RarityDistribution()

    for base in base_rows:
        row = _build_comparison_row(base, run_a.get(base.word_id), run_b.get(base.word_id), run_c.get(base.word_id), options)
        comparison_rows.append(_to_comparison_csv(row))
        dist.increment(row["final_level"])
        if row["is_outlier"]:
            outlier_rows.append(_to_outlier_csv(row))

    repo.write_rows(options.output_csv_path, COMPARISON_CSV_HEADERS, comparison_rows)
    repo.write_rows(options.outliers_csv_path, OUTLIERS_CSV_HEADERS, outlier_rows)

    print(f"Step 3 complete. Outliers={len(outlier_rows)}")
    print(f"Step 3 final {dist.format()}")
    print(f"Comparison: {options.output_csv_path}")
    print(f"Outliers: {options.outliers_csv_path}")


def _build_comparison_row(
    base: BaseWordRow,
    run_a: RunCsvRow | None,
    run_b: RunCsvRow | None,
    run_c: RunCsvRow | None,
    options: Step3Options,
) -> dict[str, object]:
    levels = [x for x in [run_a.rarity_level if run_a else None, run_b.rarity_level if run_b else None, run_c.rarity_level if run_c else None] if x is not None]
    median_level = FALLBACK_RARITY_LEVEL if not levels else median([int(x) for x in levels])
    spread = 0 if len(levels) < 2 else max(levels) - min(levels)

    confidences = [x for x in [run_a.confidence if run_a else None, run_b.confidence if run_b else None, run_c.confidence if run_c else None] if x is not None]
    low_confidence = any(x < options.confidence_threshold for x in confidences)
    is_outlier = len(levels) >= 2 and (spread >= options.outlier_threshold or low_confidence)

    reasons = []
    if spread >= options.outlier_threshold:
        reasons.append(f"spread>={options.outlier_threshold}")
    if low_confidence:
        reasons.append(f"low_confidence<{options.confidence_threshold}")

    final_level, merge_rule = _resolve_final_level(levels, median_level, options.merge_strategy)

    return {
        "word_id": base.word_id,
        "word": base.word,
        "type": base.type,
        "run_a_level": run_a.rarity_level if run_a else None,
        "run_a_confidence": run_a.confidence if run_a else None,
        "run_b_level": run_b.rarity_level if run_b else None,
        "run_b_confidence": run_b.confidence if run_b else None,
        "run_c_level": run_c.rarity_level if run_c else None,
        "run_c_confidence": run_c.confidence if run_c else None,
        "median_level": median_level,
        "spread": spread,
        "is_outlier": is_outlier,
        "reason": ";".join(reasons),
        "merge_strategy": options.merge_strategy.value,
        "merge_rule": merge_rule,
        "final_level": final_level,
    }


def _resolve_final_level(levels: list[int], median_level: int, strategy: Step3MergeStrategy) -> tuple[int, str]:
    if strategy == Step3MergeStrategy.MEDIAN:
        return median_level, "median"

    if any(x == 1 for x in levels):
        return 1, "any_level_1"
    if median_level >= 3 and any(x == 2 for x in levels):
        return 2, "any_level_2_over_median"
    if median_level in {3, 4} and any(x == 5 for x in levels):
        return 5, "any_level_5_over_median"
    return median_level, "median_fallback"


def _to_comparison_csv(row: dict[str, object]) -> list[str]:
    return [
        str(row["word_id"]),
        str(row["word"]),
        str(row["type"]),
        _opt(row["run_a_level"]),
        _opt(row["run_a_confidence"]),
        _opt(row["run_b_level"]),
        _opt(row["run_b_confidence"]),
        _opt(row["run_c_level"]),
        _opt(row["run_c_confidence"]),
        str(row["median_level"]),
        str(row["spread"]),
        str(row["is_outlier"]).lower(),
        str(row["reason"]),
        str(row["merge_strategy"]),
        str(row["merge_rule"]),
        str(row["final_level"]),
    ]


def _to_outlier_csv(row: dict[str, object]) -> list[str]:
    return [
        str(row["word_id"]),
        str(row["word"]),
        str(row["type"]),
        _opt(row["run_a_level"]),
        _opt(row["run_b_level"]),
        _opt(row["run_c_level"]),
        str(row["spread"]),
        str(row["reason"]),
    ]


def _opt(value: object) -> str:
    return "" if value is None else str(value)
