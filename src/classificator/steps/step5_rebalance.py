from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_REBALANCE_BATCH_SIZE,
    DEFAULT_REBALANCE_LOWER_RATIO,
    DEFAULT_TIMEOUT_SECONDS,
    REBALANCE_COMMON_LEVEL_PLACEHOLDER,
    REBALANCE_FROM_LEVEL_PLACEHOLDER,
    REBALANCE_OTHER_LEVEL_PLACEHOLDER,
    REBALANCE_TO_LEVEL_PLACEHOLDER,
)
from ..csv_codec import CsvFormatError
from ..distribution import RarityDistribution
from ..lm.client import LmStudioClient, ScoringContext
from ..models import BaseWordRow, ResolvedEndpoint, ScoreResult, ScoringOutputMode
from ..run_csv_repository import RunCsvRepository
from ..transitions import LevelTransition, validate_transition_set


@dataclass(frozen=True)
class Step5Options:
    run_slug: str
    model: str
    input_csv_path: Path
    output_csv_path: Path
    batch_size: int = DEFAULT_REBALANCE_BATCH_SIZE
    lower_ratio: float = DEFAULT_REBALANCE_LOWER_RATIO
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_tokens: int = DEFAULT_MAX_TOKENS
    skip_preflight: bool = False
    endpoint_option: str | None = None
    base_url_option: str | None = None
    seed: int | None = None
    transitions: list[LevelTransition] | None = None
    system_prompt: str = ""
    user_template: str = ""


@dataclass(frozen=True)
class RebalanceWord:
    word_id: int
    word: str
    type: str


@dataclass
class RebalanceDataset:
    input_headers: list[str]
    mutable_rows: list[dict[str, str]]
    words_by_id: dict[int, RebalanceWord]
    levels_by_id: dict[int, int]


@dataclass
class RebalanceRuntime:
    levels_by_id: dict[int, int]
    distribution: RarityDistribution
    rebalance_rules: dict[int, str]
    processed_word_ids: set[int]


@dataclass(frozen=True)
class Step5Logs:
    run_log_path: Path
    failed_log_path: Path
    switched_words_log_path: Path
    checkpoint_path: Path
    progress_log_path: Path


@dataclass(frozen=True)
class SwitchedWordEvent:
    word_id: int
    word: str
    type: str
    previous_level: int
    next_level: int
    rule: str
    selected_by_llm: bool


@dataclass(frozen=True)
class Step5ResumeStats:
    resumed_batches: int
    resumed_processed_words: int
    resumed_switched_words: int


@dataclass(frozen=True)
class TransitionSummary:
    transition: LevelTransition
    eligible: int
    target_assigned: int
    switched_count: int


def run_step5(options: Step5Options, *, repo: RunCsvRepository, lm_client: LmStudioClient, output_dir: Path) -> None:
    transitions = options.transitions or []
    validate_transition_set(transitions)

    dataset = _load_dataset(options.input_csv_path, repo)
    resolved_endpoint = _resolve_endpoint(options, lm_client)
    logs = _prepare_logs(output_dir, options.run_slug)
    runtime = RebalanceRuntime(
        levels_by_id=dict(dataset.levels_by_id),
        distribution=RarityDistribution.from_levels(list(dataset.levels_by_id.values())),
        rebalance_rules={},
        processed_word_ids=set(),
    )
    resume_stats = _restore_from_checkpoint(dataset, runtime, logs)

    seed = options.seed or int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    rng = random.Random(seed)

    transitions_txt = ",".join([f"{t.describe_sources()}->{t.to_level}" for t in transitions])
    print(
        f"Step 5 rebalance run='{options.run_slug}' seed={seed} batchSize={options.batch_size} "
        f"lowerRatio={options.lower_ratio:.4f} transitions={transitions_txt}"
    )
    if resume_stats.resumed_batches > 0:
        print(
            f"Step 5 resume checkpoint run='{options.run_slug}' batches={resume_stats.resumed_batches} "
            f"processed={resume_stats.resumed_processed_words} switched={resume_stats.resumed_switched_words}"
        )
    print(f"Step 5 input distribution {runtime.distribution.format()}")
    print(f"Step 5 switched words log: {logs.switched_words_log_path}")
    print(f"Step 5 progress log: {logs.progress_log_path}")

    summaries: list[TransitionSummary] = []
    for transition in transitions:
        summary = _apply_transition(
            transition=transition,
            options=options,
            dataset=dataset,
            runtime=runtime,
            resolved_endpoint=resolved_endpoint,
            logs=logs,
            lm_client=lm_client,
            rng=rng,
        )
        summaries.append(summary)

    _write_output(dataset, runtime, options, repo)

    total_switched = sum(s.switched_count for s in summaries)
    for s in summaries:
        print(
            f"Step 5 transition {s.transition.describe_sources()}->{s.transition.to_level}: "
            f"eligible={s.eligible} target_assigned={s.target_assigned} switched={s.switched_count}"
        )
    print(f"Step 5 total switched words: {total_switched}")
    print(f"Step 5 output distribution {runtime.distribution.format()}")
    print(f"Step 5 output CSV: {options.output_csv_path}")


def _load_dataset(path: Path, repo: RunCsvRepository) -> RebalanceDataset:
    table = repo.read_table(path)
    required = ["word_id", "word", "type"]
    missing = [x for x in required if x not in table.headers]
    if missing:
        raise ValueError(f"CSV {path} missing required columns: {', '.join(missing)}")

    level_column = _resolve_level_column(table.headers)
    mutable_rows = [dict(zip(table.headers, rec.values)) for rec in table.records]

    words_by_id: dict[int, RebalanceWord] = {}
    levels_by_id: dict[int, int] = {}

    for idx, row in enumerate(mutable_rows, start=2):
        try:
            word_id = int(row.get("word_id", ""))
        except Exception as exc:
            raise CsvFormatError(f"Invalid word_id at {path}:{idx}") from exc
        try:
            level = int(row.get(level_column, ""))
        except Exception as exc:
            raise CsvFormatError(f"Invalid {level_column} at {path}:{idx}") from exc
        if level < 1 or level > 5:
            raise CsvFormatError(f"{level_column} out of range at {path}:{idx}")

        words_by_id[word_id] = RebalanceWord(
            word_id=word_id,
            word=row.get("word", ""),
            type=row.get("type", ""),
        )
        levels_by_id[word_id] = level

    return RebalanceDataset(
        input_headers=list(table.headers),
        mutable_rows=mutable_rows,
        words_by_id=words_by_id,
        levels_by_id=levels_by_id,
    )


def _resolve_level_column(headers: list[str]) -> str:
    if "final_level" in headers:
        return "final_level"
    if "rarity_level" in headers:
        return "rarity_level"
    if "median_level" in headers:
        return "median_level"
    raise ValueError(f"CSV must contain one of final_level/rarity_level/median_level (got: {', '.join(headers)})")


def _resolve_endpoint(options: Step5Options, lm_client: LmStudioClient) -> ResolvedEndpoint:
    resolved = lm_client.resolve_endpoint(options.endpoint_option, options.base_url_option)
    print(f"LM endpoint: {resolved.endpoint} (flavor={resolved.flavor.value}, source={resolved.source})")
    if options.skip_preflight:
        print("Skipping LM preflight (--skip-preflight=true)")
    else:
        lm_client.preflight(resolved, options.model)
    return resolved


def _apply_transition(
    *,
    transition: LevelTransition,
    options: Step5Options,
    dataset: RebalanceDataset,
    runtime: RebalanceRuntime,
    resolved_endpoint: ResolvedEndpoint,
    logs: Step5Logs,
    lm_client: LmStudioClient,
    rng: random.Random,
) -> TransitionSummary:
    source_levels = transition.source_levels()
    remaining_by_source: dict[int, list[RebalanceWord]] = {}

    for level in source_levels:
        items = [
            w
            for w in dataset.words_by_id.values()
            if runtime.levels_by_id.get(w.word_id) == level and w.word_id not in runtime.processed_word_ids
        ]
        rng.shuffle(items)
        remaining_by_source[level] = items

    initial_source_counts = {lvl: len(remaining_by_source[lvl]) for lvl in source_levels}
    eligible_count = sum(initial_source_counts.values())
    if eligible_count == 0:
        return TransitionSummary(transition=transition, eligible=0, target_assigned=0, switched_count=0)

    processed = 0
    target_assigned = 0
    switched_count = 0
    expected_target_total = round(eligible_count * options.lower_ratio)
    batch_index = 0

    while True:
        batch = _select_stratified_batch(
            source_levels=source_levels,
            remaining_by_source_level=remaining_by_source,
            initial_source_counts=initial_source_counts,
            max_batch_size=options.batch_size,
            rng=rng,
        )
        if not batch:
            break
        batch_index += 1

        target_count = _compute_adaptive_target_count(
            processed_before_batch=processed,
            assigned_before_batch=target_assigned,
            batch_size=len(batch),
            ratio=options.lower_ratio,
            expected_total=expected_target_total,
        )
        processed += len(batch)
        batch_mix = _format_batch_source_mix(batch, runtime)

        common_level = min(transition.to_level, transition.other_level())
        common_count = target_count if transition.to_level == common_level else (len(batch) - target_count)

        if common_count <= 0:
            selected_common_word_ids: set[int] = set()
        elif common_count >= len(batch):
            selected_common_word_ids = {w.word_id for w in batch}
        else:
            scored = _score_transition_batch(
                options=options,
                transition=transition,
                common_count=common_count,
                common_level=common_level,
                batch=batch,
                resolved_endpoint=resolved_endpoint,
                logs=logs,
                lm_client=lm_client,
            )
            selected_common_word_ids = _select_common_word_ids(
                batch=batch,
                scored=scored,
                common_level=common_level,
                common_count=common_count,
            )

        switched_events = _apply_batch_assignments(
            batch=batch,
            selected_common_word_ids=selected_common_word_ids,
            transition=transition,
            runtime=runtime,
            options=options,
            logs=logs,
        )
        _append_batch_checkpoint(logs, transition, [w.word_id for w in batch], switched_events)

        assigned_to_target = len(selected_common_word_ids) if transition.to_level == common_level else (len(batch) - len(selected_common_word_ids))
        target_assigned += assigned_to_target
        switched_count += len(switched_events)

        _append_batch_progress(
            logs=logs,
            options=options,
            transition=transition,
            batch_index=batch_index,
            batch=batch,
            selected_common_word_ids=selected_common_word_ids,
            common_level=common_level,
            processed=processed,
            eligible_count=eligible_count,
            target_assigned=target_assigned,
            expected_target_total=expected_target_total,
            batch_target=target_count,
            batch_mix=batch_mix,
            runtime=runtime,
        )

        _print_switched_events(options, transition, switched_events)
        print(
            f"Step 5 progress run='{options.run_slug}' transition={transition.describe_sources()}->{transition.to_level} "
            f"processed={processed}/{eligible_count} target_assigned={target_assigned}/{expected_target_total} "
            f"batch_target={target_count} batch_mix={batch_mix} {runtime.distribution.format()}"
        )

    return TransitionSummary(
        transition=transition,
        eligible=eligible_count,
        target_assigned=target_assigned,
        switched_count=switched_count,
    )


def _select_stratified_batch(
    *,
    source_levels: list[int],
    remaining_by_source_level: dict[int, list[RebalanceWord]],
    initial_source_counts: dict[int, int],
    max_batch_size: int,
    rng: random.Random,
) -> list[RebalanceWord]:
    total_remaining = sum(len(remaining_by_source_level.get(level, [])) for level in source_levels)
    if total_remaining == 0:
        return []

    batch_size = min(max_batch_size, total_remaining)
    if len(source_levels) == 1:
        quotas = {source_levels[0]: batch_size}
    else:
        total_initial = float(sum(initial_source_counts.values()))
        quotas = {}
        for level in source_levels:
            quotas[level] = int(batch_size * ((initial_source_counts.get(level, 0) / total_initial)))

        unassigned = batch_size - sum(quotas.values())
        fractions = sorted(
            source_levels,
            key=lambda level: (batch_size * ((initial_source_counts.get(level, 0) / total_initial))) - quotas[level],
            reverse=True,
        )
        for level in fractions:
            if unassigned <= 0:
                break
            quotas[level] += 1
            unassigned -= 1

    missing = 0
    for level in source_levels:
        available = len(remaining_by_source_level.get(level, []))
        planned = quotas.get(level, 0)
        if planned > available:
            missing += planned - available
            quotas[level] = available

    while missing > 0:
        candidates = [
            level
            for level in source_levels
            if quotas.get(level, 0) < len(remaining_by_source_level.get(level, []))
        ]
        if not candidates:
            break
        candidate = max(
            candidates,
            key=lambda level: len(remaining_by_source_level.get(level, [])) - quotas.get(level, 0),
        )
        quotas[candidate] += 1
        missing -= 1

    batch: list[RebalanceWord] = []
    for level in source_levels:
        queue = remaining_by_source_level.get(level, [])
        take = quotas.get(level, 0)
        for _ in range(take):
            if queue:
                batch.append(queue.pop())

    rng.shuffle(batch)
    return batch


def _compute_adaptive_target_count(
    *,
    processed_before_batch: int,
    assigned_before_batch: int,
    batch_size: int,
    ratio: float,
    expected_total: int,
) -> int:
    if batch_size <= 0:
        return 0
    processed_after = processed_before_batch + batch_size
    desired_cumulative = round(processed_after * ratio)
    desired_cumulative = max(0, min(expected_total, desired_cumulative))
    delta = desired_cumulative - assigned_before_batch
    return max(0, min(batch_size, delta))


def _format_batch_source_mix(batch: list[RebalanceWord], runtime: RebalanceRuntime) -> str:
    counts: dict[int, int] = {}
    for word in batch:
        lvl = runtime.levels_by_id.get(word.word_id, -1)
        counts[lvl] = counts.get(lvl, 0) + 1
    parts = [f"{lvl}:{counts[lvl]}" for lvl in sorted(counts.keys())]
    return f"[{' '.join(parts)}]"


def _score_transition_batch(
    *,
    options: Step5Options,
    transition: LevelTransition,
    common_count: int,
    common_level: int,
    batch: list[RebalanceWord],
    resolved_endpoint: ResolvedEndpoint,
    logs: Step5Logs,
    lm_client: LmStudioClient,
) -> list[ScoreResult]:
    scoring_ctx = ScoringContext(
        run_slug=f"{options.run_slug}_{transition.describe_sources().replace('-', '_')}_{transition.to_level}",
        model=options.model,
        endpoint=resolved_endpoint.endpoint,
        max_retries=options.max_retries,
        timeout_seconds=options.timeout_seconds,
        run_log_path=logs.run_log_path,
        failed_log_path=logs.failed_log_path,
        system_prompt=_render_template(options.system_prompt, transition, common_level),
        user_template=_render_template(options.user_template, transition, common_level),
        flavor=resolved_endpoint.flavor,
        max_tokens=options.max_tokens,
        allow_partial_results=False,
        expected_json_items=common_count,
        output_mode=ScoringOutputMode.SELECTED_WORD_IDS,
        forced_rarity_level=common_level,
    )
    base_rows = [BaseWordRow(word_id=w.word_id, word=w.word, type=w.type) for w in batch]
    return lm_client.score_batch_resilient(base_rows, scoring_ctx)


def _select_common_word_ids(
    *,
    batch: list[RebalanceWord],
    scored: list[ScoreResult],
    common_level: int,
    common_count: int,
) -> set[int]:
    batch_ids = {w.word_id for w in batch}
    selected = []
    seen = set()
    for s in scored:
        if s.word_id in batch_ids and s.rarity_level == common_level and s.word_id not in seen:
            seen.add(s.word_id)
            selected.append(s.word_id)
    if len(selected) != common_count:
        raise RuntimeError(
            f"Expected exactly {common_count} selected word_ids, got {len(selected)}. Prompt/parse contract violation."
        )
    return set(selected)


def _apply_batch_assignments(
    *,
    batch: list[RebalanceWord],
    selected_common_word_ids: set[int],
    transition: LevelTransition,
    runtime: RebalanceRuntime,
    options: Step5Options,
    logs: Step5Logs,
) -> list[SwitchedWordEvent]:
    common_level = min(transition.to_level, transition.other_level())
    rare_level = max(transition.to_level, transition.other_level())

    switched_events: list[SwitchedWordEvent] = []
    for word in batch:
        next_level = common_level if word.word_id in selected_common_word_ids else rare_level
        previous = runtime.levels_by_id.get(word.word_id)
        runtime.levels_by_id[word.word_id] = next_level
        runtime.distribution.set_level(previous, next_level)
        runtime.processed_word_ids.add(word.word_id)

        if previous != next_level:
            rule = f"{transition.describe_sources()}->{next_level} (via {transition.describe_sources()}:{transition.to_level})"
            runtime.rebalance_rules[word.word_id] = rule
            ev = SwitchedWordEvent(
                word_id=word.word_id,
                word=word.word,
                type=word.type,
                previous_level=(previous if previous is not None else -1),
                next_level=next_level,
                rule=rule,
                selected_by_llm=word.word_id in selected_common_word_ids,
            )
            switched_events.append(ev)
            _log_switched_word(logs, options, transition, ev)
    return switched_events


def _log_switched_word(logs: Step5Logs, options: Step5Options, transition: LevelTransition, switched: SwitchedWordEvent) -> None:
    payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "run_slug": options.run_slug,
        "model": options.model,
        "word_id": switched.word_id,
        "word": switched.word,
        "type": switched.type,
        "previous_level": switched.previous_level,
        "new_level": switched.next_level,
        "selected_by_llm": switched.selected_by_llm,
        "transition": f"{transition.describe_sources()}->{transition.to_level}",
    }
    _append_json_line(logs.switched_words_log_path, payload)


def _append_batch_checkpoint(logs: Step5Logs, transition: LevelTransition, processed_word_ids: list[int], switched_events: list[SwitchedWordEvent]) -> None:
    payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "transition": f"{transition.describe_sources()}->{transition.to_level}",
        "processed_word_ids": processed_word_ids,
        "switched": [
            {"word_id": ev.word_id, "new_level": ev.next_level, "rule": ev.rule}
            for ev in switched_events
        ],
    }
    _append_json_line(logs.checkpoint_path, payload)


def _append_batch_progress(
    *,
    logs: Step5Logs,
    options: Step5Options,
    transition: LevelTransition,
    batch_index: int,
    batch: list[RebalanceWord],
    selected_common_word_ids: set[int],
    common_level: int,
    processed: int,
    eligible_count: int,
    target_assigned: int,
    expected_target_total: int,
    batch_target: int,
    batch_mix: str,
    runtime: RebalanceRuntime,
) -> None:
    batch_by_id = {w.word_id: w for w in batch}
    selected_common_sorted = sorted(selected_common_word_ids)

    if transition.to_level == common_level:
        target_word_ids = selected_common_sorted
    else:
        target_word_ids = sorted([w.word_id for w in batch if w.word_id not in selected_common_word_ids])

    payload = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "run_slug": options.run_slug,
        "transition": f"{transition.describe_sources()}->{transition.to_level}",
        "batch_index": batch_index,
        "batch_size": len(batch),
        "processed": processed,
        "eligible_total": eligible_count,
        "remaining": max(0, eligible_count - processed),
        "target_assigned": target_assigned,
        "target_expected_total": expected_target_total,
        "batch_target": batch_target,
        "batch_mix": batch_mix,
        "selected_common_level": common_level,
        "selected_common_count": len(selected_common_sorted),
        "selected_common_word_ids": selected_common_sorted,
        "selected_common_words": [batch_by_id[word_id].word for word_id in selected_common_sorted if word_id in batch_by_id],
        "picked_target_level": transition.to_level,
        "picked_target_count": len(target_word_ids),
        "picked_target_word_ids": target_word_ids,
        "picked_target_words": [batch_by_id[word_id].word for word_id in target_word_ids if word_id in batch_by_id],
        "distribution": {
            "1": runtime.distribution.count(1),
            "2": runtime.distribution.count(2),
            "3": runtime.distribution.count(3),
            "4": runtime.distribution.count(4),
            "5": runtime.distribution.count(5),
        },
    }
    _append_json_line(logs.progress_log_path, payload)


def _restore_from_checkpoint(dataset: RebalanceDataset, runtime: RebalanceRuntime, logs: Step5Logs) -> Step5ResumeStats:
    if not logs.checkpoint_path.exists():
        return Step5ResumeStats(0, 0, 0)

    resumed_batches = 0
    resumed_processed = 0
    resumed_switched = 0
    applied_switched_ids: set[int] = set()

    with logs.checkpoint_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            node = json.loads(line)
            resumed_batches += 1

            processed = node.get("processed_word_ids")
            if isinstance(processed, list):
                for pid in processed:
                    try:
                        word_id = int(pid)
                    except Exception:
                        continue
                    if word_id > 0 and word_id in dataset.words_by_id and word_id not in runtime.processed_word_ids:
                        runtime.processed_word_ids.add(word_id)
                        resumed_processed += 1

            switched = node.get("switched")
            if isinstance(switched, list):
                for item in switched:
                    if not isinstance(item, dict):
                        continue
                    try:
                        word_id = int(item.get("word_id", -1))
                        new_level = int(item.get("new_level", -1))
                    except Exception:
                        continue
                    rule = str(item.get("rule", ""))
                    if word_id <= 0 or new_level not in {1, 2, 3, 4, 5}:
                        continue
                    if word_id not in dataset.words_by_id or word_id in applied_switched_ids:
                        continue
                    applied_switched_ids.add(word_id)
                    previous = runtime.levels_by_id.get(word_id)
                    runtime.levels_by_id[word_id] = new_level
                    runtime.distribution.set_level(previous, new_level)
                    if rule:
                        runtime.rebalance_rules[word_id] = rule
                    resumed_switched += 1

    return Step5ResumeStats(resumed_batches, resumed_processed, resumed_switched)


def _print_switched_events(options: Step5Options, transition: LevelTransition, switched_events: list[SwitchedWordEvent]) -> None:
    if not switched_events:
        return
    selected = [ev for ev in switched_events if ev.selected_by_llm]
    not_selected = [ev for ev in switched_events if not ev.selected_by_llm]
    print(
        f"Step 5 switched run='{options.run_slug}' transition={transition.describe_sources()}->{transition.to_level} changed={len(switched_events)}"
    )
    _print_switched_group("selected", selected)
    _print_switched_group("not", not_selected)


def _print_switched_group(label: str, events: list[SwitchedWordEvent]) -> None:
    if not events:
        return
    chunks = [events[i : i + 7] for i in range(0, len(events), 7)]
    for idx, chunk in enumerate(chunks):
        prefix = f"  {label}: " if idx == 0 else "    "
        content = " | ".join(
            [
                f"{ev.word}({'+' if ev.next_level > ev.previous_level else '-' if ev.next_level < ev.previous_level else '='})"
                for ev in chunk
            ]
        )
        print(prefix + content)


def _write_output(dataset: RebalanceDataset, runtime: RebalanceRuntime, options: Step5Options, repo: RunCsvRepository) -> None:
    headers = list(dataset.input_headers)
    for col in ["final_level", "rebalance_rule", "rebalance_model", "rebalance_run", "rebalanced_at"]:
        if col not in headers:
            headers.append(col)

    rebalanced_at = datetime.now(tz=timezone.utc).isoformat()
    rows: list[list[str]] = []
    for row in dataset.mutable_rows:
        try:
            word_id = int(row.get("word_id", ""))
        except Exception as exc:
            raise CsvFormatError("Invalid word_id in memory while writing output") from exc

        final_level = runtime.levels_by_id.get(word_id)
        if final_level is None:
            raise CsvFormatError(f"Missing level for word_id={word_id}")

        row["final_level"] = str(final_level)
        changed = word_id in runtime.rebalance_rules
        row["rebalance_rule"] = runtime.rebalance_rules.get(word_id, "")
        row["rebalance_model"] = options.model if changed else row.get("rebalance_model", "")
        row["rebalance_run"] = options.run_slug if changed else row.get("rebalance_run", "")
        row["rebalanced_at"] = rebalanced_at if changed else row.get("rebalanced_at", "")

        rows.append([row.get(h, "") for h in headers])

    repo.write_table_atomic(options.output_csv_path, headers, rows)


def _render_template(template: str, transition: LevelTransition, common_level: int) -> str:
    source_label = transition.describe_sources()
    return (
        template.replace(REBALANCE_FROM_LEVEL_PLACEHOLDER, source_label)
        .replace(REBALANCE_TO_LEVEL_PLACEHOLDER, str(transition.to_level))
        .replace(REBALANCE_OTHER_LEVEL_PLACEHOLDER, str(transition.other_level()))
        .replace(REBALANCE_COMMON_LEVEL_PLACEHOLDER, str(common_level))
    )


def _prepare_logs(output_dir: Path, run_slug: str) -> Step5Logs:
    runs_dir = output_dir / "rebalance" / "runs"
    failed_dir = output_dir / "rebalance" / "failed_batches"
    switched_dir = output_dir / "rebalance" / "switched_words"
    checkpoint_dir = output_dir / "rebalance" / "checkpoints"
    progress_dir = output_dir / "rebalance" / "progress"

    runs_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    switched_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    progress_dir.mkdir(parents=True, exist_ok=True)

    return Step5Logs(
        run_log_path=runs_dir / f"{run_slug}.jsonl",
        failed_log_path=failed_dir / f"{run_slug}.failed.jsonl",
        switched_words_log_path=switched_dir / f"{run_slug}.switched.jsonl",
        checkpoint_path=checkpoint_dir / f"{run_slug}.checkpoint.jsonl",
        progress_log_path=progress_dir / f"{run_slug}.progress.jsonl",
    )


def _append_json_line(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")
