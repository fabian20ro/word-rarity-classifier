from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..run_csv_repository import RunCsvRepository

_DEFAULT_LEVEL_COLUMNS = ("final_level", "rarity_level", "median_level")


@dataclass(frozen=True)
class RarityDistributionResult:
    csv_path: Path
    level_column: str
    total_rows: int
    distribution: dict[int, int]


def run_rarity_distribution(
    *,
    csv_path: Path,
    repo: RunCsvRepository,
    level_column: str | None = None,
) -> RarityDistributionResult:
    table = repo.read_table(csv_path)
    resolved_level_col = _resolve_level_column(table.headers, level_column)
    idx_level = table.headers.index(resolved_level_col)

    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total_rows = 0

    for rec in table.records:
        vals = rec.values
        if len(vals) == 1 and vals[0] == "":
            continue
        total_rows += 1
        if idx_level >= len(vals):
            raise ValueError(f"Missing {resolved_level_col} at row {rec.line_number} in {csv_path}")
        raw_level = vals[idx_level].strip()
        try:
            level = int(raw_level)
        except Exception as exc:
            raise ValueError(f"Invalid {resolved_level_col} '{raw_level}' at row {rec.line_number} in {csv_path}") from exc
        if level < 1 or level > 5:
            raise ValueError(f"Invalid {resolved_level_col} {level} at row {rec.line_number} in {csv_path}")
        distribution[level] += 1

    print(f"input_csv={csv_path}")
    print(f"level_column={resolved_level_col}")
    print(
        f"distribution=[1:{distribution[1]} 2:{distribution[2]} 3:{distribution[3]} "
        f"4:{distribution[4]} 5:{distribution[5]}] total={total_rows}"
    )
    print(
        "distribution_pct=["
        f"1:{_pct(distribution[1], total_rows):.2f}% "
        f"2:{_pct(distribution[2], total_rows):.2f}% "
        f"3:{_pct(distribution[3], total_rows):.2f}% "
        f"4:{_pct(distribution[4], total_rows):.2f}% "
        f"5:{_pct(distribution[5], total_rows):.2f}%]"
    )

    return RarityDistributionResult(
        csv_path=csv_path,
        level_column=resolved_level_col,
        total_rows=total_rows,
        distribution=distribution,
    )


def _resolve_level_column(headers: list[str], level_column: str | None) -> str:
    if level_column:
        if level_column not in headers:
            raise ValueError(f"CSV missing requested level column '{level_column}'")
        return level_column
    for col in _DEFAULT_LEVEL_COLUMNS:
        if col in headers:
            return col
    raise ValueError("CSV missing level column: final_level/rarity_level/median_level")


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return (part * 100.0) / total
