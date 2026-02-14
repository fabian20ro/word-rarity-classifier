from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class LmApiFlavor(str, Enum):
    OPENAI_COMPAT = "openai_compat"
    LMSTUDIO_REST = "lmstudio_rest"


class UploadMode(str, Enum):
    PARTIAL = "partial"
    FULL_FALLBACK = "full-fallback"

    @classmethod
    def parse(cls, value: str | None) -> "UploadMode":
        v = (value or "partial").strip().lower()
        if v in {"partial", ""}:
            return cls.PARTIAL
        if v in {"full-fallback", "full_fallback"}:
            return cls.FULL_FALLBACK
        raise ValueError(f"Invalid upload mode: {value}")


class Step3MergeStrategy(str, Enum):
    MEDIAN = "median"
    ANY_EXTREMES = "any_extremes"

    @classmethod
    def parse(cls, value: str | None) -> "Step3MergeStrategy":
        v = (value or "median").strip().lower()
        if v in {"median", ""}:
            return cls.MEDIAN
        if v in {"any-extremes", "any_extremes", "three-any-extremes", "three_any_extremes"}:
            return cls.ANY_EXTREMES
        raise ValueError(f"Invalid merge strategy: {value}")


class ScoringOutputMode(str, Enum):
    SCORE_RESULTS = "score_results"
    SELECTED_WORD_IDS = "selected_word_ids"


@dataclass(frozen=True)
class BaseWordRow:
    word_id: int
    word: str
    type: str


@dataclass(frozen=True)
class RunCsvRow:
    word_id: int
    word: str
    type: str
    rarity_level: int
    tag: str
    confidence: float
    scored_at: str
    model: str
    run_slug: str


@dataclass(frozen=True)
class ScoreResult:
    word_id: int
    word: str
    type: str
    rarity_level: int
    tag: str
    confidence: float


@dataclass(frozen=True)
class WordLevel:
    word_id: int
    rarity_level: int


@dataclass(frozen=True)
class ResolvedEndpoint:
    endpoint: str
    models_endpoint: str | None
    flavor: LmApiFlavor
    source: str


@dataclass(frozen=True)
class BatchAttempt:
    scores: list[ScoreResult]
    unresolved: list[BaseWordRow]
    last_error: str | None
    connectivity_failure: bool


@dataclass(frozen=True)
class ParsedBatch:
    scores: list[ScoreResult]
    unresolved: list[BaseWordRow]


@dataclass(frozen=True)
class RunBaseline:
    count: int
    min_id: int | None
    max_id: int | None


@dataclass(frozen=True)
class UploadMarkerResult:
    marker_path: Path
    used_companion_file: bool
    marked_rows: int


@dataclass(frozen=True)
class LmModelConfig:
    model_id: str
    temperature: float = 0.0
    top_k: int | None = 40
    top_p: float | None = 1.0
    min_p: float | None = None
    repeat_penalty: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens_cap: int | None = None
    reasoning_effort: str | None = None
    enable_thinking: bool | None = None
    thinking_type: str | None = None

    def has_reasoning_controls(self) -> bool:
        return any(
            [
                self.reasoning_effort is not None,
                self.enable_thinking is not None,
                self.thinking_type is not None,
            ]
        )
