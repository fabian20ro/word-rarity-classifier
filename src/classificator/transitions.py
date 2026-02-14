from __future__ import annotations

from dataclasses import dataclass

from .constants import DEFAULT_REBALANCE_TRANSITIONS


@dataclass(frozen=True)
class LevelTransition:
    from_level: int
    to_level: int
    from_level_upper: int | None = None

    def source_levels(self) -> list[int]:
        if self.from_level_upper is None:
            return [self.from_level]
        return [self.from_level, self.from_level_upper]

    def describe_sources(self) -> str:
        if self.from_level_upper is None:
            return str(self.from_level)
        return f"{self.from_level}-{self.from_level_upper}"

    def other_level(self) -> int:
        if self.from_level_upper is not None:
            for level in self.source_levels():
                if level != self.to_level:
                    return level
            raise ValueError("Invalid pair transition")
        if self.to_level == self.from_level:
            return min(5, self.to_level + 1)
        return self.from_level


def require_valid_transition(from_level: int, to_level: int) -> None:
    valid_range = 1 <= from_level <= 5 and 1 <= to_level <= 5
    valid_relation = to_level == from_level - 1 or to_level == from_level
    invalid_top_self_split = from_level == 5 and to_level == 5
    if not (valid_range and valid_relation and not invalid_top_self_split):
        raise ValueError(
            f"Invalid transition '{from_level}:{to_level}'. Allowed: one-step downgrade (3:2) or keep+promote split (2:2); 5:5 forbidden."
        )


def require_valid_pair_transition(from_lower: int, from_upper: int, to_level: int) -> None:
    if not (1 <= from_lower <= 5 and 1 <= from_upper <= 5 and 1 <= to_level <= 5):
        raise ValueError("Pair transition levels must be in 1..5")
    if from_upper != from_lower + 1:
        raise ValueError("Pair transition source levels must be consecutive")
    if to_level not in {from_lower, from_upper}:
        raise ValueError("Pair transition target must be one of the source levels")


def validate_transition_set(transitions: list[LevelTransition]) -> None:
    if not transitions:
        raise ValueError("At least one transition is required")
    seen: dict[int, int] = {}
    duplicates: set[int] = set()
    for idx, t in enumerate(transitions):
        for level in t.source_levels():
            if level in seen and seen[level] != idx:
                duplicates.add(level)
            seen[level] = idx
    if duplicates:
        dup = ", ".join(str(x) for x in sorted(duplicates))
        raise ValueError(f"Transitions must not overlap source levels: {dup}")


def parse_transitions(raw: str | None) -> list[LevelTransition]:
    input_text = (raw or DEFAULT_REBALANCE_TRANSITIONS).strip()
    out: list[LevelTransition] = []
    for token in input_text.split(","):
        parts = token.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid transition token '{token}'. Expected from:to or from-from:to")
        src = parts[0].strip()
        to_level = int(parts[1].strip())
        if "-" in src:
            lo_s, hi_s = src.split("-", 1)
            lo = int(lo_s.strip())
            hi = int(hi_s.strip())
            require_valid_pair_transition(lo, hi, to_level)
            out.append(LevelTransition(from_level=lo, from_level_upper=hi, to_level=to_level))
        else:
            fr = int(src)
            require_valid_transition(fr, to_level)
            out.append(LevelTransition(from_level=fr, to_level=to_level))

    deduped: dict[tuple[int, int, int | None], LevelTransition] = {
        (t.from_level, t.to_level, t.from_level_upper): t for t in out
    }
    result = sorted(deduped.values(), key=lambda t: (t.from_level, t.from_level_upper or t.from_level, t.to_level))
    validate_transition_set(result)
    return result
