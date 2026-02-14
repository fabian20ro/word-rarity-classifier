from __future__ import annotations

import json
from enum import Enum

from ..constants import USER_INPUT_PLACEHOLDER
from ..models import BaseWordRow, LmModelConfig


class ResponseFormatMode(str, Enum):
    NONE = "none"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


class JsonSchemaKind(str, Enum):
    SCORE_RESULTS = "score_results"
    SELECTED_WORD_IDS = "selected_word_ids"


class LmStudioRequestBuilder:
    SCORE_MIN_MAX_TOKENS = 256
    SCORE_TOKENS_PER_ITEM = 40
    SCORE_BASE_TOKENS = 200

    SELECTION_MIN_MAX_TOKENS = 128
    SELECTION_TOKENS_PER_ITEM = 24
    SELECTION_BASE_TOKENS = 128
    SELECTION_HARD_MAX_TOKENS = 1024

    def build_request(
        self,
        *,
        model: str,
        batch: list[BaseWordRow],
        system_prompt: str,
        user_template: str,
        response_format_mode: ResponseFormatMode,
        include_reasoning_controls: bool,
        config: LmModelConfig,
        max_tokens: int,
        expected_items: int | None = None,
        schema_kind: JsonSchemaKind = JsonSchemaKind.SCORE_RESULTS,
    ) -> str:
        if schema_kind == JsonSchemaKind.SCORE_RESULTS:
            entries = [
                {"word_id": row.word_id, "word": row.word, "type": row.type}
                for row in batch
            ]
        else:
            entries = [
                {"local_id": idx + 1, "word": row.word}
                for idx, row in enumerate(batch)
            ]

        entries_json = json.dumps(entries, ensure_ascii=False)
        if USER_INPUT_PLACEHOLDER in user_template:
            user_prompt = user_template.replace(USER_INPUT_PLACEHOLDER, entries_json)
        else:
            user_prompt = f"{user_template}\n\nIntrări:\n{entries_json}"

        if schema_kind == JsonSchemaKind.SCORE_RESULTS:
            estimated = len(batch) * self.SCORE_TOKENS_PER_ITEM + self.SCORE_BASE_TOKENS
            effective = max(self.SCORE_MIN_MAX_TOKENS, min(estimated, max_tokens))
        else:
            expected = max(1, expected_items or 1)
            estimated = expected * self.SELECTION_TOKENS_PER_ITEM + self.SELECTION_BASE_TOKENS
            effective = max(self.SELECTION_MIN_MAX_TOKENS, min(estimated, max_tokens))
            effective = min(effective, self.SELECTION_HARD_MAX_TOKENS)

        if config.max_tokens_cap is not None:
            effective = min(effective, config.max_tokens_cap)

        payload: dict[str, object] = {
            "model": model,
            "temperature": config.temperature,
            "max_tokens": effective,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if config.top_k is not None:
            payload["top_k"] = config.top_k
        if config.top_p is not None:
            payload["top_p"] = config.top_p
        if config.min_p is not None:
            payload["min_p"] = config.min_p
        if config.repeat_penalty is not None:
            payload["repeat_penalty"] = config.repeat_penalty
        if config.frequency_penalty is not None:
            payload["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty is not None:
            payload["presence_penalty"] = config.presence_penalty

        if include_reasoning_controls:
            if config.reasoning_effort is not None:
                payload["reasoning_effort"] = config.reasoning_effort
            if config.thinking_type is not None:
                payload["thinking"] = {"type": config.thinking_type}
            if config.enable_thinking is not None:
                payload["chat_template_kwargs"] = {"enable_thinking": config.enable_thinking}

        if response_format_mode == ResponseFormatMode.JSON_OBJECT:
            payload["response_format"] = {"type": "json_object"}
        elif response_format_mode == ResponseFormatMode.JSON_SCHEMA:
            expected = expected_items or len(batch)
            if schema_kind == JsonSchemaKind.SCORE_RESULTS:
                payload["response_format"] = _score_results_schema(expected)
            else:
                payload["response_format"] = _selected_word_ids_schema(expected_items=expected, max_local_id=len(batch))

        return json.dumps(payload, ensure_ascii=False)


def _score_results_schema(expected_items: int) -> dict[str, object]:
    expected = max(1, expected_items)
    item_schema = {
        "type": "object",
        "properties": {
            "word_id": {"type": "integer"},
            "word": {"type": "string"},
            "type": {"type": "string"},
            "rarity_level": {"type": "integer", "minimum": 1, "maximum": 5},
            "tag": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["word_id", "word", "type", "rarity_level", "tag", "confidence"],
        "additionalProperties": False,
    }
    schema = {
        "type": "array",
        "items": item_schema,
        "minItems": expected,
        "maxItems": expected,
    }
    return {"type": "json_schema", "json_schema": {"name": "rarity_batch_array", "schema": schema}}


def _selected_word_ids_schema(expected_items: int, max_local_id: int) -> dict[str, object]:
    expected = max(1, expected_items)
    bounded_max = max(1, max_local_id)
    schema = {
        "type": "array",
        "items": {"type": "integer", "minimum": 1, "maximum": bounded_max},
        "minItems": expected,
        "maxItems": expected,
        "uniqueItems": True,
    }
    return {"type": "json_schema", "json_schema": {"name": "selected_word_ids", "schema": schema}}
