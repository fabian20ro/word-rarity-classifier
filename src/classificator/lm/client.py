from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..constants import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    LMSTUDIO_CHAT_PATH,
    LMSTUDIO_MODELS_PATH,
    MODEL_CRASH_BACKOFF_SECONDS,
    OPENAI_CHAT_COMPLETIONS_PATH,
    OPENAI_MODELS_PATH,
    REBALANCE_COMMON_COUNT_PLACEHOLDER,
    REBALANCE_TARGET_COUNT_PLACEHOLDER,
)
from ..models import (
    BaseWordRow,
    BatchAttempt,
    LmApiFlavor,
    ParsedBatch,
    ResolvedEndpoint,
    ScoreResult,
    ScoringOutputMode,
)
from ..step2_metrics import Step2Metrics, categorize_error
from .model_profiles import resolve_model_config
from .request_builder import JsonSchemaKind, LmStudioRequestBuilder, ResponseFormatMode
from .response_parser import LmStudioResponseParser

MAX_RECURSION_DEPTH = 10
JSON_SCHEMA_UNRESOLVED_DISABLE_RATIO = 0.2
SELECTION_REPAIR_MAX_RETRIES = 1

SELECTION_REPAIR_SYSTEM_PROMPT = """
Ești selector lexical pentru limba română.
Alege cele mai comune intrări din listă (uz curent, vorbire de zi cu zi în România).

Răspunsul trebuie să fie STRICT JSON valid: un array de numere întregi.
Fiecare număr trebuie să fie un `local_id` din input.
Nu adăuga text extra, explicații, markdown sau blocuri de cod.
Nu inventa id-uri. Fără duplicate.
Evită termeni vulgari/obsceni când există alternative.
""".strip()

SELECTION_REPAIR_USER_TEMPLATE = """
Returnează DOAR JSON valid: array de întregi `local_id`.
Fără text extra, fără markdown, fără blocuri de cod.
Selectează cele mai comune intrări din listă.
Numărul exact de id-uri este impus de schema JSON; respectă schema.

Input:
{{INPUT_JSON}}
""".strip()


@dataclass(frozen=True)
class ScoringContext:
    run_slug: str
    model: str
    endpoint: str
    max_retries: int
    timeout_seconds: int
    run_log_path: Path
    failed_log_path: Path
    system_prompt: str
    user_template: str
    flavor: LmApiFlavor
    max_tokens: int
    allow_partial_results: bool = False
    expected_json_items: int | None = None
    output_mode: ScoringOutputMode = ScoringOutputMode.SCORE_RESULTS
    forced_rarity_level: int | None = None


@dataclass(frozen=True)
class CapabilityState:
    response_format_mode: ResponseFormatMode = ResponseFormatMode.JSON_OBJECT
    reasoning_controls_supported: bool = True


class LmStudioClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        metrics: Step2Metrics | None = None,
        request_builder: LmStudioRequestBuilder | None = None,
        response_parser: LmStudioResponseParser | None = None,
    ) -> None:
        self.api_key = api_key
        self.metrics = metrics
        self.request_builder = request_builder or LmStudioRequestBuilder()
        self.response_parser = response_parser or LmStudioResponseParser(metrics=metrics)
        self.capability_state = CapabilityState()
        self._requests = _load_requests()

    def resolve_endpoint(self, endpoint_option: str | None, base_url_option: str | None) -> ResolvedEndpoint:
        if endpoint_option and endpoint_option.strip():
            normalized = endpoint_option.strip()
            parsed = urlparse(normalized)
            path = parsed.path or ""
            if not path or path == "/":
                return self._detect_from_base(normalized, source="explicit-base")
            explicit = self._resolve_explicit_endpoint(normalized, path)
            if explicit is not None:
                return explicit
            return ResolvedEndpoint(
                endpoint=normalized,
                models_endpoint=None,
                flavor=LmApiFlavor.OPENAI_COMPAT,
                source="explicit-endpoint-unknown-path",
            )

        base_url = (base_url_option or DEFAULT_LMSTUDIO_BASE_URL).strip().rstrip("/")
        return self._detect_from_base(base_url, source="auto")

    def preflight(self, resolved_endpoint: ResolvedEndpoint, model: str) -> None:
        if not resolved_endpoint.models_endpoint:
            return
        resp = self._get_json(resolved_endpoint.models_endpoint, timeout_seconds=DEFAULT_PREFLIGHT_TIMEOUT_SECONDS)
        if resp.status_code < 200 or resp.status_code > 299:
            raise RuntimeError(
                f"LM preflight failed: HTTP {resp.status_code} from {resolved_endpoint.models_endpoint}"
            )
        if model not in resp.text:
            print(f"Warning: model '{model}' not found in {resolved_endpoint.models_endpoint} response.")

    def score_batch_resilient(self, batch: list[BaseWordRow], context: ScoringContext) -> list[ScoreResult]:
        return self._score_batch_resilient_internal(batch, context, depth=0)

    def _score_batch_resilient_internal(self, batch: list[BaseWordRow], ctx: ScoringContext, depth: int) -> list[ScoreResult]:
        if depth >= MAX_RECURSION_DEPTH:
            for word in batch:
                self._log_failed_word(ctx, word, "max_recursion_depth_exceeded", depth=depth)
            return []

        if ctx.output_mode == ScoringOutputMode.SELECTED_WORD_IDS:
            expected = ctx.expected_json_items
            forced = ctx.forced_rarity_level
            if expected is None:
                raise ValueError("expected_json_items is required for selected-id mode")
            if forced is None:
                raise ValueError("forced_rarity_level is required for selected-id mode")
            if expected <= 0:
                return []
            if expected >= len(batch):
                return [
                    ScoreResult(
                        word_id=row.word_id,
                        word=row.word,
                        type=row.type,
                        rarity_level=forced,
                        tag="common",
                        confidence=0.9,
                    )
                    for row in batch
                ]

        direct = self._try_score_batch(batch, ctx)
        if direct.connectivity_failure:
            raise RuntimeError(f"LM request failed due connectivity/timeout at {ctx.endpoint}: {direct.last_error}")

        if direct.scores:
            if ctx.allow_partial_results:
                return direct.scores
            if not direct.unresolved:
                return direct.scores
            retried = self._score_batch_resilient_internal(direct.unresolved, ctx, depth + 1)
            return direct.scores + retried

        if (
            ctx.output_mode == ScoringOutputMode.SELECTED_WORD_IDS
            and _is_selection_count_mismatch(direct.last_error)
        ):
            repaired = self._try_selection_repair_before_split(batch, ctx)
            if repaired is not None:
                return repaired

        if len(batch) == 1:
            self._log_failed_word(ctx, batch[0], "batch_failed_after_retries", last_error=direct.last_error)
            return []

        split_idx = len(batch) // 2
        left_batch = batch[:split_idx]
        right_batch = batch[split_idx:]

        if ctx.output_mode == ScoringOutputMode.SELECTED_WORD_IDS:
            total_expected = ctx.expected_json_items
            if total_expected is None:
                raise ValueError("expected_json_items is required for selected-id mode")
            left_expected = _compute_split_expected(total_expected, len(left_batch), len(batch))
            right_expected = total_expected - left_expected
            left_ctx = replace(ctx, expected_json_items=left_expected)
            right_ctx = replace(ctx, expected_json_items=right_expected)
        else:
            left_ctx = ctx
            right_ctx = ctx

        return self._score_batch_resilient_internal(left_batch, left_ctx, depth + 1) + self._score_batch_resilient_internal(
            right_batch, right_ctx, depth + 1
        )

    def _try_score_batch(self, batch: list[BaseWordRow], ctx: ScoringContext) -> BatchAttempt:
        last_error: str | None = None
        saw_only_connectivity_failures = True

        config = resolve_model_config(ctx.model)
        response_format_mode = self._response_format_mode_for(ctx.flavor)
        include_reasoning_controls = self._should_include_reasoning_controls(ctx.flavor, config)
        schema_kind = (
            JsonSchemaKind.SCORE_RESULTS
            if ctx.output_mode == ScoringOutputMode.SCORE_RESULTS
            else JsonSchemaKind.SELECTED_WORD_IDS
        )

        resolved_system_prompt, resolved_user_template = self._resolve_selection_prompt_counts(ctx)

        for attempt in range(ctx.max_retries):
            response_body: str | None = None
            payload = self.request_builder.build_request(
                model=ctx.model,
                batch=batch,
                system_prompt=resolved_system_prompt,
                user_template=resolved_user_template,
                response_format_mode=response_format_mode,
                include_reasoning_controls=include_reasoning_controls,
                config=config,
                max_tokens=ctx.max_tokens,
                expected_items=ctx.expected_json_items,
                schema_kind=schema_kind,
            )
            try:
                resp = self._post_json(ctx.endpoint, payload, timeout_seconds=ctx.timeout_seconds)
                response_body = resp.text
                if resp.status_code < 200 or resp.status_code > 299:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

                parsed = self.response_parser.parse(
                    batch=batch,
                    response_body=resp.text,
                    output_mode=ctx.output_mode,
                    forced_rarity_level=ctx.forced_rarity_level,
                    expected_items=ctx.expected_json_items,
                )

                disable_after_partial = (
                    response_format_mode == ResponseFormatMode.JSON_SCHEMA
                    and _should_disable_response_format_after_partial_schema_parse(
                        len(batch), len(parsed.unresolved)
                    )
                )
                if disable_after_partial:
                    self._mark_response_format_disabled()
                    response_format_mode = ResponseFormatMode.NONE

                self._append_json_line(
                    ctx.run_log_path,
                    {
                        "ts": _now_iso(),
                        "run": ctx.run_slug,
                        "attempt": attempt + 1,
                        "batch_size": len(batch),
                        "parsed_count": len(parsed.scores),
                        "unresolved_count": len(parsed.unresolved),
                        "allow_partial_results": ctx.allow_partial_results,
                        "disable_response_format_after_partial_parse": disable_after_partial,
                        "response_format_mode": response_format_mode.value,
                        "reasoning_controls_enabled": include_reasoning_controls,
                        "request": _to_json_node_or_string(payload),
                        "response": _to_json_node_or_string(resp.text),
                    },
                )

                return BatchAttempt(
                    scores=parsed.scores,
                    unresolved=parsed.unresolved,
                    last_error=None,
                    connectivity_failure=False,
                )
            except Exception as exc:
                last_error = str(exc)
                connectivity_failure = _is_connectivity_failure(exc)
                unsupported_response_format = (
                    response_format_mode != ResponseFormatMode.NONE
                    and _is_unsupported_response_format(exc)
                )
                should_switch_schema = (
                    response_format_mode == ResponseFormatMode.JSON_OBJECT
                    and _should_switch_to_json_schema(exc)
                )
                unsupported_reasoning_controls = (
                    include_reasoning_controls and _is_unsupported_reasoning_controls(exc)
                )
                empty_parsed = (
                    response_format_mode == ResponseFormatMode.JSON_SCHEMA
                    and _is_empty_parsed_results(exc)
                )
                model_crash = _is_model_crash(exc)

                if not connectivity_failure:
                    saw_only_connectivity_failures = False
                if self.metrics:
                    self.metrics.record_error(categorize_error(last_error))

                self._append_json_line(
                    ctx.run_log_path,
                    {
                        "ts": _now_iso(),
                        "run": ctx.run_slug,
                        "attempt": attempt + 1,
                        "batch_size": len(batch),
                        "error": last_error,
                        "connectivity_failure": connectivity_failure,
                        "unsupported_response_format": unsupported_response_format,
                        "switch_to_json_schema": should_switch_schema,
                        "unsupported_reasoning_controls": unsupported_reasoning_controls,
                        "empty_parsed_results": empty_parsed,
                        "response_format_mode": response_format_mode.value,
                        "reasoning_controls_enabled": include_reasoning_controls,
                        "model_crash": model_crash,
                        "request": _to_json_node_or_string(payload),
                        "response_excerpt": _excerpt_for_log(response_body),
                    },
                )

                if should_switch_schema:
                    self._mark_response_format_json_schema()
                    response_format_mode = ResponseFormatMode.JSON_SCHEMA
                elif unsupported_response_format or empty_parsed:
                    self._mark_response_format_disabled()
                    response_format_mode = ResponseFormatMode.NONE

                if unsupported_reasoning_controls:
                    self._mark_reasoning_controls_unsupported()
                    include_reasoning_controls = False

                if model_crash:
                    time.sleep(MODEL_CRASH_BACKOFF_SECONDS * (attempt + 1))

        print(f"Batch failed after retries (size={len(batch)}): {last_error}")
        return BatchAttempt(
            scores=[],
            unresolved=batch,
            last_error=last_error,
            connectivity_failure=saw_only_connectivity_failures,
        )

    def _try_selection_repair_before_split(self, batch: list[BaseWordRow], ctx: ScoringContext) -> list[ScoreResult] | None:
        expected = ctx.expected_json_items
        if expected is None or expected <= 0 or expected >= len(batch):
            return None

        repair_ctx = replace(
            ctx,
            run_slug=f"{ctx.run_slug}_repair",
            max_retries=SELECTION_REPAIR_MAX_RETRIES,
            system_prompt=SELECTION_REPAIR_SYSTEM_PROMPT,
            user_template=SELECTION_REPAIR_USER_TEMPLATE,
            allow_partial_results=False,
        )
        repaired = self._try_score_batch(batch, repair_ctx)
        if repaired.connectivity_failure:
            return None
        if repaired.unresolved:
            return None
        if len(repaired.scores) != expected:
            return None

        print(f"Selection repair succeeded (size={len(batch)}, expected={expected}), avoiding recursive split.")
        return repaired.scores

    def _resolve_selection_prompt_counts(self, ctx: ScoringContext) -> tuple[str, str]:
        if ctx.output_mode != ScoringOutputMode.SELECTED_WORD_IDS:
            return ctx.system_prompt, ctx.user_template
        expected = ctx.expected_json_items
        if expected is None:
            return ctx.system_prompt, ctx.user_template
        return (
            self._apply_selection_count_placeholders(ctx.system_prompt, expected),
            self._apply_selection_count_placeholders(ctx.user_template, expected),
        )

    def _apply_selection_count_placeholders(self, prompt: str, expected: int) -> str:
        return (
            prompt.replace(REBALANCE_TARGET_COUNT_PLACEHOLDER, str(expected)).replace(
                REBALANCE_COMMON_COUNT_PLACEHOLDER, str(expected)
            )
        )

    def _response_format_mode_for(self, flavor: LmApiFlavor) -> ResponseFormatMode:
        if flavor != LmApiFlavor.OPENAI_COMPAT:
            return ResponseFormatMode.NONE
        return self.capability_state.response_format_mode

    def _should_include_reasoning_controls(self, flavor: LmApiFlavor, config) -> bool:
        if flavor != LmApiFlavor.OPENAI_COMPAT:
            return False
        if not config.has_reasoning_controls():
            return False
        return self.capability_state.reasoning_controls_supported

    def _mark_response_format_json_schema(self) -> None:
        if self.capability_state.response_format_mode != ResponseFormatMode.JSON_SCHEMA:
            self.capability_state = replace(self.capability_state, response_format_mode=ResponseFormatMode.JSON_SCHEMA)
            print("LM capability: switching response_format to json_schema for this run.")

    def _mark_response_format_disabled(self) -> None:
        if self.capability_state.response_format_mode != ResponseFormatMode.NONE:
            self.capability_state = replace(self.capability_state, response_format_mode=ResponseFormatMode.NONE)
            print("LM capability: disabling response_format for this run.")

    def _mark_reasoning_controls_unsupported(self) -> None:
        if self.capability_state.reasoning_controls_supported:
            self.capability_state = replace(self.capability_state, reasoning_controls_supported=False)
            print("LM capability: disabling reasoning controls for this run.")

    def _resolve_explicit_endpoint(self, endpoint: str, path: str) -> ResolvedEndpoint | None:
        if "/api/v1/chat" in path:
            base = endpoint.split("/api/v1/chat", 1)[0]
            return ResolvedEndpoint(
                endpoint=endpoint,
                models_endpoint=f"{base}{LMSTUDIO_MODELS_PATH}",
                flavor=LmApiFlavor.LMSTUDIO_REST,
                source="explicit-endpoint",
            )
        if "/v1/chat/completions" in path:
            base = endpoint.split("/v1/chat/completions", 1)[0]
            return ResolvedEndpoint(
                endpoint=endpoint,
                models_endpoint=f"{base}{OPENAI_MODELS_PATH}",
                flavor=LmApiFlavor.OPENAI_COMPAT,
                source="explicit-endpoint",
            )
        return None

    def _detect_from_base(self, base_url: str, source: str) -> ResolvedEndpoint:
        openai_models_url = f"{base_url}{OPENAI_MODELS_PATH}"
        if self._probe(openai_models_url):
            return ResolvedEndpoint(
                endpoint=f"{base_url}{OPENAI_CHAT_COMPLETIONS_PATH}",
                models_endpoint=openai_models_url,
                flavor=LmApiFlavor.OPENAI_COMPAT,
                source=f"{source}-openai",
            )

        lm_models_url = f"{base_url}{LMSTUDIO_MODELS_PATH}"
        if self._probe(lm_models_url):
            return ResolvedEndpoint(
                endpoint=f"{base_url}{LMSTUDIO_CHAT_PATH}",
                models_endpoint=lm_models_url,
                flavor=LmApiFlavor.LMSTUDIO_REST,
                source=f"{source}-lmstudio",
            )

        return ResolvedEndpoint(
            endpoint=f"{base_url}{OPENAI_CHAT_COMPLETIONS_PATH}",
            models_endpoint=openai_models_url,
            flavor=LmApiFlavor.OPENAI_COMPAT,
            source=f"{source}-fallback",
        )

    def _probe(self, url: str) -> bool:
        try:
            resp = self._get_json(url, timeout_seconds=DEFAULT_PREFLIGHT_TIMEOUT_SECONDS)
            return 200 <= resp.status_code <= 299
        except Exception:
            return False

    def _headers(self, include_content_type: bool) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if include_content_type:
            h["Content-Type"] = "application/json"
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get_json(self, url: str, *, timeout_seconds: int):
        return self._requests.get(url, timeout=timeout_seconds, headers=self._headers(False))

    def _post_json(self, url: str, payload: str, *, timeout_seconds: int):
        return self._requests.post(
            url, data=payload.encode("utf-8"), timeout=timeout_seconds, headers=self._headers(True)
        )

    def _log_failed_word(self, ctx: ScoringContext, word: BaseWordRow, error: str, **extra: Any) -> None:
        payload: dict[str, Any] = {
            "ts": _now_iso(),
            "run": ctx.run_slug,
            "word_id": word.word_id,
            "word": word.word,
            "type": word.type,
            "error": error,
        }
        payload.update(extra)
        self._append_json_line(ctx.failed_log_path, payload)

    def _append_json_line(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")


def _compute_split_expected(total_expected: int, left_size: int, total_size: int) -> int:
    if total_expected <= 0 or left_size <= 0 or total_size <= 0:
        return 0
    if left_size >= total_size:
        return total_expected
    raw = total_expected * left_size / total_size
    return int(round(raw))


def _should_disable_response_format_after_partial_schema_parse(batch_size: int, unresolved_count: int) -> bool:
    if batch_size <= 0 or unresolved_count <= 0:
        return False
    threshold = max(1, int((batch_size * JSON_SCHEMA_UNRESOLVED_DISABLE_RATIO) + 0.9999))
    return unresolved_count >= threshold


def _is_connectivity_failure(exc: Exception) -> bool:
    requests_mod = _load_requests()
    if isinstance(exc, (requests_mod.Timeout, requests_mod.ConnectionError, socket.timeout, TimeoutError)):
        return True
    msg = str(exc).lower()
    return "timed out" in msg or "connection refused" in msg or "couldn't connect" in msg


def _is_model_crash(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("model" in msg and "crash" in msg) or "exit code" in msg


def _error_text(exc: Exception) -> str:
    return f"{exc}".lower()


def _is_unsupported_response_format(exc: Exception) -> bool:
    text = _error_text(exc)
    if "response_format" not in text:
        return False
    return any(tok in text for tok in ["unsupported", "unknown", "must be", "json_schema", "json object"])


def _should_switch_to_json_schema(exc: Exception) -> bool:
    text = _error_text(exc)
    return "response_format" in text and "must be" in text and "json_schema" in text


def _is_unsupported_reasoning_controls(exc: Exception) -> bool:
    text = _error_text(exc)
    mentions = any(tok in text for tok in ["reasoning_effort", "thinking", "chat_template_kwargs", "enable_thinking"])
    if not mentions:
        return False
    return any(tok in text for tok in ["unsupported", "unknown", "unexpected", "invalid"])


def _is_empty_parsed_results(exc: Exception) -> bool:
    return "no valid results parsed from 0 result nodes" in _error_text(exc)


def _excerpt_for_log(content: str | None, max_chars: int = 500) -> str | None:
    if not content:
        return None
    compact = " ".join(content.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "...(truncated)"


def _to_json_node_or_string(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _is_selection_count_mismatch(last_error: str | None) -> bool:
    text = (last_error or "").lower()
    return "expected exactly" in text and "selected" in text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_requests():
    try:
        import requests  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing dependency 'requests'. Install project dependencies with: pip install -e .") from exc
    return requests
