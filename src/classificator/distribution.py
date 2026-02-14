from __future__ import annotations


class RarityDistribution:
    def __init__(self) -> None:
        self._counts = [0, 0, 0, 0, 0, 0]

    @classmethod
    def from_levels(cls, levels: list[int] | tuple[int, ...] | set[int]) -> "RarityDistribution":
        d = cls()
        for level in levels:
            d.increment(level)
        return d

    def increment(self, level: int) -> None:
        if 1 <= level <= 5:
            self._counts[level] += 1

    def set_level(self, previous_level: int | None, new_level: int) -> None:
        if previous_level is not None and 1 <= previous_level <= 5 and self._counts[previous_level] > 0:
            self._counts[previous_level] -= 1
        if 1 <= new_level <= 5:
            self._counts[new_level] += 1

    def count(self, level: int) -> int:
        return self._counts[level]

    def format(self) -> str:
        total = sum(self._counts[1:6])
        parts = []
        for level in range(1, 6):
            count = self._counts[level]
            pct = (count * 100.0 / total) if total > 0 else 0.0
            parts.append(f"{level}:{count}({pct:.1f}%)")
        return f"distribution=[{' '.join(parts)}]"
