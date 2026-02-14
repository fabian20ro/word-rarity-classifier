from __future__ import annotations

from pathlib import Path


def sanitize_run_slug(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "_")
    valid = "".join(ch for ch in normalized if ch.isalnum() or ch == "_")
    if not (1 <= len(valid) <= 40):
        raise ValueError(
            f"Invalid run slug '{raw}'. Allowed: lowercase alnum + underscore, max 40 chars"
        )
    return valid


def median(values: list[int]) -> int:
    if not values:
        raise ValueError("median() requires non-empty values")
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 1:
        return sorted_vals[mid]
    return round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0)


def load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file does not exist: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Prompt file is empty: {path}")
    return content


def required_columns(actual: list[str], required: list[str], label: str) -> None:
    missing = [col for col in required if col not in actual]
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")
