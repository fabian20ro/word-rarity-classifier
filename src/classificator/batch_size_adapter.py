from __future__ import annotations

from collections import deque


class BatchSizeAdapter:
    def __init__(self, initial_size: int, min_size: int = 3, window_size: int = 10) -> None:
        if initial_size < min_size:
            raise ValueError("initial_size must be >= min_size")
        if min_size < 1:
            raise ValueError("min_size must be >= 1")
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.initial_size = initial_size
        self.min_size = min_size
        self.window_size = window_size
        self.current_size = initial_size
        self.outcomes: deque[bool] = deque()

    def recommended_size(self) -> int:
        return self.current_size

    def record_outcome(self, success_ratio: float) -> None:
        normalized = max(0.0, min(1.0, success_ratio))
        success = normalized >= 0.9
        self.outcomes.append(success)
        while len(self.outcomes) > self.window_size:
            self.outcomes.popleft()
        self._adjust_size()

    def success_rate(self) -> float:
        if not self.outcomes:
            return 1.0
        return sum(1 for ok in self.outcomes if ok) / len(self.outcomes)

    def _adjust_size(self) -> None:
        rate = self.success_rate()
        if rate < 0.5:
            self.current_size = max(self.min_size, (self.current_size * 2) // 3)
        elif rate > 0.9:
            self.current_size = min(self.initial_size, (self.current_size * 3) // 2)
