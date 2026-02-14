from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Step2Metrics:
    started_at: datetime = field(default_factory=datetime.utcnow)
    total_scored: int = 0
    total_failed: int = 0
    total_batches: int = 0
    successful_batches: int = 0
    repaired_json_count: int = 0
    fuzzy_match_count: int = 0
    partial_extraction_count: int = 0
    error_counts: Counter[str] = field(default_factory=Counter)

    def record_batch_result(self, batch_size: int, scored_count: int) -> None:
        self.total_batches += 1
        self.total_scored += scored_count
        self.total_failed += batch_size - scored_count
        if scored_count > 0:
            self.successful_batches += 1
        if 0 < scored_count < batch_size:
            self.partial_extraction_count += 1

    def record_error(self, category: str) -> None:
        self.error_counts[category] += 1

    def record_json_repair(self) -> None:
        self.repaired_json_count += 1

    def record_fuzzy_match(self) -> None:
        self.fuzzy_match_count += 1

    def elapsed_seconds(self) -> float:
        return max(0.0, (datetime.utcnow() - self.started_at).total_seconds())

    def words_per_minute(self) -> float:
        elapsed = self.elapsed_seconds()
        if elapsed < 1:
            return 0.0
        return self.total_scored * 60.0 / elapsed

    def success_rate(self) -> float:
        if self.total_batches == 0:
            return 1.0
        return self.successful_batches / self.total_batches

    def eta(self, remaining_words: int) -> timedelta:
        wpm = self.words_per_minute()
        if wpm < 0.1:
            return timedelta(0)
        seconds = int((remaining_words / wpm) * 60.0)
        return timedelta(seconds=seconds)

    def format_progress(self, remaining: int, effective_batch_size: int) -> str:
        return (
            f"scored={self.total_scored} failed={self.total_failed} remaining={remaining} "
            f"wpm={self.words_per_minute():.1f} eta={format_duration(self.eta(remaining))} "
            f"batch_size={effective_batch_size} success_rate={self.success_rate() * 100:.0f}%"
        )

    def format_summary(self) -> str:
        lines = [
            "--- Step 2 Run Summary ---",
            f"Duration: {format_duration(timedelta(seconds=int(self.elapsed_seconds())))}",
            f"Words scored: {self.total_scored}, failed: {self.total_failed}",
            f"Batches: {self.total_batches} (success_rate={self.success_rate() * 100:.0f}%)",
            f"Throughput: {self.words_per_minute():.1f} words/min",
            f"JSON repairs: {self.repaired_json_count}",
            f"Fuzzy matches: {self.fuzzy_match_count}",
            f"Partial extractions: {self.partial_extraction_count}",
        ]
        if self.error_counts:
            ranked = sorted(self.error_counts.items(), key=lambda item: item[1], reverse=True)
            lines.append("Errors: " + ", ".join(f"{k}={v}" for k, v in ranked if v > 0))
        return "\n".join(lines)


def categorize_error(message: str | None) -> str:
    if message is None:
        return "OTHER"
    lower = message.lower()
    if "missing" in lower and "content" in lower:
        return "MISSING_CONTENT"
    if any(x in lower for x in ["truncat", "unclosed", "unexpected end", "premature"]):
        return "TRUNCATED_JSON"
    if "decimal" in lower or "number format" in lower:
        return "DECIMAL_FORMAT"
    if "mismatch" in lower and "word" in lower:
        return "WORD_MISMATCH"
    if "model" in lower and ("crash" in lower or "exit code" in lower):
        return "MODEL_CRASH"
    if "timed out" in lower or "connection refused" in lower or ("connect" in lower and "fail" in lower):
        return "CONNECTIVITY"
    return "OTHER"


def format_duration(d: timedelta) -> str:
    total = int(d.total_seconds())
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours > 0:
        return f"{hours}h{minutes}m{seconds}s"
    if minutes > 0:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"
