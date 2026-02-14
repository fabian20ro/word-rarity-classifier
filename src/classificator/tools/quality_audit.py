from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..run_csv_repository import RunCsvRepository


@dataclass(frozen=True)
class QualityAuditResult:
    distribution: dict[int, int]
    total_rows: int
    level_column: str
    l1_jaccard: float | None
    l1_intersection: int | None
    l1_candidate_size: int
    l1_reference_size: int | None
    anchor_precision: float | None
    anchor_recall: float | None
    passed: bool
    failures: list[str]


def run_quality_audit(
    *,
    candidate_csv: Path,
    reference_csv: Path | None = None,
    anchor_l1_file: Path | None = None,
    min_l1_jaccard: float | None = None,
    min_anchor_l1_precision: float | None = None,
    min_anchor_l1_recall: float | None = None,
    repo: RunCsvRepository,
) -> QualityAuditResult:
    candidate = _load_run(candidate_csv, repo)
    failures: list[str] = []

    l1_jaccard = None
    l1_intersection = None
    l1_reference_size = None

    print(f"candidate_csv={candidate_csv}")
    print(f"candidate_level_column={candidate['level_column']}")
    dist = candidate["distribution"]
    print(
        f"candidate_distribution=[1:{dist[1]} 2:{dist[2]} 3:{dist[3]} 4:{dist[4]} 5:{dist[5]}] total={candidate['total_rows']}"
    )

    if reference_csv is not None:
        reference = _load_run(reference_csv, repo)
        inter = len(candidate["l1_word_ids"].intersection(reference["l1_word_ids"]))
        union = len(candidate["l1_word_ids"]) + len(reference["l1_word_ids"]) - inter
        jaccard = _ratio(inter, union)
        l1_jaccard = jaccard
        l1_intersection = inter
        l1_reference_size = len(reference["l1_word_ids"])
        print(
            f"l1_jaccard={jaccard:.4f} intersection={inter} candidate_l1={len(candidate['l1_word_ids'])} "
            f"reference_l1={len(reference['l1_word_ids'])}"
        )
        if min_l1_jaccard is not None and jaccard < min_l1_jaccard:
            failures.append(f"l1_jaccard {jaccard:.4f} < min {min_l1_jaccard:.4f}")

    anchor_precision = None
    anchor_recall = None
    if anchor_l1_file is not None:
        anchors = _load_anchor_words(anchor_l1_file)
        inter = len(candidate["l1_words"].intersection(anchors))
        precision = _ratio(inter, len(candidate["l1_words"]))
        recall = _ratio(inter, len(anchors))
        anchor_precision = precision
        anchor_recall = recall
        print(
            f"anchor_l1_precision={precision:.4f} ({inter}/{len(candidate['l1_words'])}) "
            f"anchor_l1_recall={recall:.4f} ({inter}/{len(anchors)})"
        )
        if min_anchor_l1_precision is not None and precision < min_anchor_l1_precision:
            failures.append(f"anchor_l1_precision {precision:.4f} < min {min_anchor_l1_precision:.4f}")
        if min_anchor_l1_recall is not None and recall < min_anchor_l1_recall:
            failures.append(f"anchor_l1_recall {recall:.4f} < min {min_anchor_l1_recall:.4f}")

    passed = not failures
    if passed:
        print("quality_gate=PASS")
    else:
        print("quality_gate=FAIL")
        for f in failures:
            print(f"- {f}")

    return QualityAuditResult(
        distribution=dist,
        total_rows=candidate["total_rows"],
        level_column=candidate["level_column"],
        l1_jaccard=l1_jaccard,
        l1_intersection=l1_intersection,
        l1_candidate_size=len(candidate["l1_word_ids"]),
        l1_reference_size=l1_reference_size,
        anchor_precision=anchor_precision,
        anchor_recall=anchor_recall,
        passed=passed,
        failures=failures,
    )


def _load_run(path: Path, repo: RunCsvRepository) -> dict[str, object]:
    table = repo.read_table(path)
    if "word_id" not in table.headers or "word" not in table.headers:
        raise ValueError(f"CSV must contain word_id and word: {path}")
    if "final_level" in table.headers:
        level_col = "final_level"
    elif "rarity_level" in table.headers:
        level_col = "rarity_level"
    elif "median_level" in table.headers:
        level_col = "median_level"
    else:
        raise ValueError("CSV missing level column: final_level/rarity_level/median_level")

    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    l1_word_ids: set[int] = set()
    l1_words: set[str] = set()
    total_rows = 0

    headers = table.headers
    idx_word_id = headers.index("word_id")
    idx_word = headers.index("word")
    idx_level = headers.index(level_col)

    for rec in table.records:
        vals = rec.values
        if len(vals) == 1 and vals[0] == "":
            continue
        total_rows += 1
        word_id = int(vals[idx_word_id])
        level = int(vals[idx_level])
        if level < 1 or level > 5:
            raise ValueError(f"Invalid level at row {rec.line_number} in {path}")
        word = vals[idx_word].strip()
        distribution[level] += 1
        if level == 1:
            l1_word_ids.add(word_id)
            if word:
                l1_words.add(word.lower())

    return {
        "path": str(path),
        "level_column": level_col,
        "total_rows": total_rows,
        "distribution": distribution,
        "l1_word_ids": l1_word_ids,
        "l1_words": l1_words,
    }


def _load_anchor_words(path: Path) -> set[str]:
    words: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        words.add(t.lower())
    if not words:
        raise ValueError(f"Anchor file has no usable words: {path}")
    return words


def _ratio(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return n / d
