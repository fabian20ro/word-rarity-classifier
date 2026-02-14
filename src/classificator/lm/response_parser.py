from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..fuzzy_word_matcher import matches as fuzzy_matches
from ..json_repair import repair as repair_json
from ..models import BaseWordRow, ParsedBatch, ScoreResult, ScoringOutputMode
from ..step2_metrics import Step2Metrics


@dataclass(frozen=True)
class ScoreCandidate:
    word_id: int | None
    word: str | None
    type: str | None
    rarity_level: int | None
    tag: str
    confidence: float


@dataclass(frozen=True)
class SelectionCandidate:
    returned_id: int | None
    word: str | None


SELECTION_EDGE_PUNCTUATION = re.compile(r"^[^\w\d]+|[^\w\d]+$")


class LmStudioResponseParser:
    def __init__(self, metrics: Step2Metrics | None = None) -> None:
        self.metrics = metrics

    def parse(
        self,
        *,
        batch: list[BaseWordRow],
        response_body: str,
        output_mode: ScoringOutputMode = ScoringOutputMode.SCORE_RESULTS,
        forced_rarity_level: int | None = None,
        expected_items: int | None = None,
    ) -> ParsedBatch:
        root = json.loads(response_body)
        content = self._extract_model_content(root)
        if not content:
            raise RuntimeError("LM response missing assistant content")

        repaired = repair_json(content)
        if repaired != content and self.metrics:
            self.metrics.record_json_repair()

        content_json = self._parse_content_json(repaired)
        results = self._extract_results_array(content_json)

        if output_mode == ScoringOutputMode.SELECTED_WORD_IDS:
            return self._parse_selected_word_ids(
                batch=batch,
                results=results,
                forced_rarity_level=forced_rarity_level,
                expected_items=expected_items,
            )
        return self._parse_results_lenient(batch=batch, results=results)

    def _parse_selected_word_ids(
        self,
        *,
        batch: list[BaseWordRow],
        results: list[object],
        forced_rarity_level: int | None,
        expected_items: int | None,
    ) -> ParsedBatch:
        rarity_level = forced_rarity_level if forced_rarity_level in {1, 2, 3, 4, 5} else None
        if rarity_level is None:
            raise ValueError("forced_rarity_level is required for selected-word-id mode")
        expected = expected_items if expected_items and expected_items > 0 else None
        if expected is None:
            raise ValueError("expected_items is required for selected-word-id mode")

        if not batch:
            return ParsedBatch(scores=[], unresolved=[])

        batch_by_id = {r.word_id: r for r in batch}
        batch_by_local = {idx + 1: row for idx, row in enumerate(batch)}

        raw: list[SelectionCandidate] = []
        for node in results:
            node_id = None
            word = None
            if isinstance(node, int):
                node_id = node
            elif isinstance(node, str):
                try:
                    node_id = int(node)
                except Exception:
                    node_id = None
            elif isinstance(node, dict):
                node_id = _to_int(node.get("local_id"))
                if node_id is None:
                    node_id = _to_int(node.get("word_id"))
                if node_id is None:
                    node_id = _to_int(node)
                raw_word = node.get("word")
                word = str(raw_word).strip() if raw_word is not None else None
                if word == "":
                    word = None
            if node_id is not None or word is not None:
                raw.append(SelectionCandidate(returned_id=node_id, word=word))

        selected = self._coerce_selections_to_word_ids(
            raw_selections=raw,
            batch=batch,
            batch_by_id=batch_by_id,
            batch_by_local_id=batch_by_local,
            expected=expected,
        )
        if len(selected) != expected:
            raise RuntimeError(
                f"Expected exactly {expected} selected ids, got {len(selected)} for batch of {len(batch)}"
            )

        scores = [
            ScoreResult(
                word_id=batch_by_id[word_id].word_id,
                word=batch_by_id[word_id].word,
                type=batch_by_id[word_id].type,
                rarity_level=rarity_level,
                tag="common",
                confidence=0.9,
            )
            for word_id in selected
        ]
        return ParsedBatch(scores=scores, unresolved=[])

    def _coerce_selections_to_word_ids(
        self,
        *,
        raw_selections: list[SelectionCandidate],
        batch: list[BaseWordRow],
        batch_by_id: dict[int, BaseWordRow],
        batch_by_local_id: dict[int, BaseWordRow],
        expected: int,
    ) -> list[int]:
        if expected <= 0 or not batch:
            return []

        selected: list[int] = []
        selected_set: set[int] = set()

        # 1) strict local_id only
        for candidate in raw_selections:
            local_id = candidate.returned_id
            if local_id is None:
                continue
            if local_id in batch_by_local_id:
                wid = batch_by_local_id[local_id].word_id
                if wid not in selected_set:
                    selected_set.add(wid)
                    selected.append(wid)
            if len(selected) == expected:
                return selected

        # 2) fallback by word matching
        if len(selected) < expected:
            remaining = {wid: row for wid, row in batch_by_id.items() if wid not in selected_set}
            for candidate in raw_selections:
                if len(selected) == expected:
                    return selected
                if candidate.returned_id is not None and candidate.returned_id in batch_by_local_id:
                    continue
                if not candidate.word:
                    continue
                raw_word = candidate.word.strip()
                exact_key = raw_word.lower()
                norm_key = _normalize_selection_word(raw_word)
                matched = None
                for row in remaining.values():
                    if row.word.lower() == exact_key or (
                        norm_key and _normalize_selection_word(row.word) == norm_key
                    ):
                        matched = row
                        break
                if matched is None:
                    continue
                if matched.word_id not in selected_set:
                    selected_set.add(matched.word_id)
                    selected.append(matched.word_id)
                    remaining.pop(matched.word_id, None)
            if len(selected) == expected:
                return selected

        # 3) positional fallback (0-based or 1-based)
        if selected:
            return selected
        distinct_ids = []
        seen = set()
        for candidate in raw_selections:
            if candidate.returned_id is not None and candidate.returned_id not in seen:
                seen.add(candidate.returned_id)
                distinct_ids.append(candidate.returned_id)
        if not distinct_ids:
            return []
        has_zero = 0 in distinct_ids
        base = 0 if has_zero else 1

        indices: list[int] = []
        seen_idx: set[int] = set()
        for raw_id in distinct_ids:
            idx = raw_id - base
            if 0 <= idx < len(batch) and idx not in seen_idx:
                seen_idx.add(idx)
                indices.append(idx)
            if len(indices) == expected:
                break
        return [batch[idx].word_id for idx in indices]

    def _parse_results_lenient(self, *, batch: list[BaseWordRow], results: list[object]) -> ParsedBatch:
        if not batch:
            return ParsedBatch(scores=[], unresolved=[])

        pending_by_id = {row.word_id: row for row in batch}
        pending_by_word_type: dict[tuple[str, str], list[BaseWordRow]] = {}
        for row in batch:
            pending_by_word_type.setdefault((row.word, row.type), []).append(row)

        scored: list[ScoreResult] = []
        for node in results:
            candidate = self._parse_score_candidate(node)
            if candidate is None:
                continue
            matched = self._match_candidate(candidate, pending_by_id, pending_by_word_type)
            if matched is None:
                continue
            scored.append(
                ScoreResult(
                    word_id=matched.word_id,
                    word=matched.word,
                    type=matched.type,
                    rarity_level=int(candidate.rarity_level),
                    tag=(candidate.tag or "uncertain")[:16],
                    confidence=candidate.confidence,
                )
            )

        unresolved = sorted(pending_by_id.values(), key=lambda r: r.word_id)
        if not scored and len(unresolved) == len(batch):
            raise RuntimeError(
                f"No valid results parsed from {len(results)} result nodes for batch of {len(batch)}"
            )
        if unresolved and self.metrics:
            self.metrics.record_error("WORD_MISMATCH")
        return ParsedBatch(scores=scored, unresolved=unresolved)

    def _parse_score_candidate(self, node: object) -> ScoreCandidate | None:
        if not isinstance(node, dict):
            return None
        rarity = _to_int(node.get("rarity_level"))
        if rarity not in {1, 2, 3, 4, 5}:
            return None

        confidence = _normalize_confidence(node.get("confidence"))
        return ScoreCandidate(
            word_id=_to_int(node.get("word_id")),
            word=_to_str_or_none(node.get("word")),
            type=_to_str_or_none(node.get("type")),
            rarity_level=rarity,
            tag=str(node.get("tag") or "uncertain"),
            confidence=confidence,
        )

    def _match_candidate(
        self,
        candidate: ScoreCandidate,
        pending_by_id: dict[int, BaseWordRow],
        pending_by_word_type: dict[tuple[str, str], list[BaseWordRow]],
    ) -> BaseWordRow | None:
        if candidate.word_id is not None and candidate.word_id in pending_by_id:
            row = pending_by_id.pop(candidate.word_id)
            key = (row.word, row.type)
            queue = pending_by_word_type.get(key)
            if queue:
                pending_by_word_type[key] = [x for x in queue if x.word_id != row.word_id]
                if not pending_by_word_type[key]:
                    pending_by_word_type.pop(key, None)
            return row

        if not candidate.word or not candidate.type:
            return None

        key = (candidate.word, candidate.type)
        queue = pending_by_word_type.get(key)
        if queue:
            row = queue.pop(0)
            if not queue:
                pending_by_word_type.pop(key, None)
            pending_by_id.pop(row.word_id, None)
            return row

        fuzzy_key = None
        for (w, t), rows in pending_by_word_type.items():
            if t == candidate.type and rows and fuzzy_matches(w, candidate.word):
                fuzzy_key = (w, t)
                break
        if fuzzy_key is None:
            return None

        row = pending_by_word_type[fuzzy_key].pop(0)
        if not pending_by_word_type[fuzzy_key]:
            pending_by_word_type.pop(fuzzy_key, None)
        pending_by_id.pop(row.word_id, None)
        if self.metrics:
            self.metrics.record_fuzzy_match()
        return row

    def _extract_model_content(self, root: object) -> str | None:
        if not isinstance(root, dict):
            return None

        choices = root.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0]
            if isinstance(msg, dict):
                message = msg.get("message")
                if isinstance(message, dict):
                    val = _content_text(message.get("content"))
                    if val:
                        return val

        message = root.get("message")
        if isinstance(message, dict):
            val = _content_text(message.get("content"))
            if val:
                return val

        return _content_text(root.get("output_text"))

    def _parse_content_json(self, content: str) -> object:
        try:
            node = json.loads(content)
            if not isinstance(node, (dict, list)):
                raise RuntimeError("LM content is not a JSON object/array")
            return node
        except Exception:
            pass

        first = _extract_first_json_block(content)
        if first is None:
            excerpt = _excerpt(content)
            raise RuntimeError(f"LM content is not valid JSON. Excerpt: {excerpt}")

        try:
            node = json.loads(first)
            if not isinstance(node, (dict, list)):
                raise RuntimeError("LM content is not a JSON object/array")
            return node
        except Exception:
            salvaged = _salvage_results_from_malformed_content(first)
            if salvaged is not None:
                if self.metrics:
                    self.metrics.record_json_repair()
                return salvaged
            excerpt = _excerpt(first)
            raise RuntimeError(f"LM content JSON parse failed. Excerpt: {excerpt}")

    def _extract_results_array(self, content_json: object) -> list[object]:
        if isinstance(content_json, list):
            return content_json
        if isinstance(content_json, dict):
            for key in ["results", "items", "data", "predictions"]:
                val = content_json.get(key)
                if isinstance(val, list):
                    return val
            for val in content_json.values():
                if isinstance(val, list):
                    return val
            keys = ",".join(content_json.keys())
            raise RuntimeError(f"LM content has no results array. keys=[{keys}]")
        raise RuntimeError(f"LM content must be JSON object/array, got {type(content_json)!r}")


def _to_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except Exception:
            return None
    return None


def _to_str_or_none(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _normalize_confidence(value: object) -> float:
    if isinstance(value, (int, float)):
        v = float(value)
    elif isinstance(value, str):
        try:
            v = float(value)
        except Exception:
            v = float("nan")
    else:
        v = float("nan")

    if v != v:  # nan
        return 0.5
    if 0.0 <= v <= 1.0:
        return v
    if 1.0 < v <= 100.0:
        return v / 100.0
    return 0.5


def _content_text(node: object) -> str | None:
    if node is None:
        return None
    raw: str
    if isinstance(node, str):
        raw = node
    elif isinstance(node, list):
        parts: list[str] = []
        for part in node:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str):
                    parts.append(t)
        raw = "".join(parts)
    elif isinstance(node, dict):
        raw = json.dumps(node, ensure_ascii=False)
    else:
        raw = str(node)

    stripped = _strip_code_fences(raw).strip()
    return stripped or None


def _strip_code_fences(content: str) -> str:
    trimmed = content.strip()
    if not trimmed.startswith("```"):
        return trimmed
    out = trimmed
    for prefix in ["```json", "```JSON", "```"]:
        if out.startswith(prefix):
            out = out[len(prefix) :]
            break
    if out.endswith("```"):
        out = out[: -3]
    return out.strip()


def _extract_first_json_block(content: str) -> str | None:
    start = -1
    for idx, ch in enumerate(content):
        if ch in "[{":
            start = idx
            break
    if start < 0:
        return None

    obj_depth = 0
    arr_depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            obj_depth += 1
        elif ch == "}":
            obj_depth -= 1
        elif ch == "[":
            arr_depth += 1
        elif ch == "]":
            arr_depth -= 1

        if obj_depth == 0 and arr_depth == 0 and i >= start:
            return content[start : i + 1].strip()

    return None


def _salvage_results_from_malformed_content(content: str) -> dict[str, object] | None:
    arr_slice = _extract_likely_results_array_slice(content)
    if not arr_slice:
        return None
    objs = _extract_top_level_object_slices(arr_slice)
    if not objs:
        return None
    results: list[object] = []
    for raw in objs:
        repaired = repair_json(raw)
        try:
            node = json.loads(repaired)
        except Exception:
            continue
        if isinstance(node, dict):
            results.append(node)
    if not results:
        return None
    return {"results": results}


def _extract_likely_results_array_slice(content: str) -> str | None:
    trimmed = content.strip()
    if trimmed.startswith("["):
        return trimmed
    idx_results = content.find('"results"')
    search_from = idx_results if idx_results >= 0 else 0
    arr_start = content.find("[", search_from)
    if arr_start < 0:
        return None
    arr_end = _find_matching(content, arr_start, "[", "]")
    if arr_end < 0:
        return None
    return content[arr_start : arr_end + 1]


def _find_matching(text: str, start: int, opener: str, closer: str) -> int:
    if start < 0 or start >= len(text) or text[start] != opener:
        return -1
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_top_level_object_slices(array_slice: str) -> list[str]:
    slices: list[str] = []
    obj_depth = 0
    in_string = False
    escaped = False
    start = -1
    for i, ch in enumerate(array_slice):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if obj_depth == 0:
                start = i
            obj_depth += 1
        elif ch == "}":
            if obj_depth > 0:
                obj_depth -= 1
                if obj_depth == 0 and start >= 0:
                    slices.append(array_slice[start : i + 1])
                    start = -1
    return slices


def _normalize_selection_word(value: str) -> str:
    if not value.strip():
        return ""
    lowered = value.lower().strip().replace("’", "'")
    return SELECTION_EDGE_PUNCTUATION.sub("", lowered)


def _excerpt(content: str, max_chars: int = 500) -> str:
    compact = " ".join(content.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "...(truncated)"
