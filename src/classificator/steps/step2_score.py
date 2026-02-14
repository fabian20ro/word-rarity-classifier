from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..batch_size_adapter import BatchSizeAdapter
from ..constants import DEFAULT_BATCH_SIZE, DEFAULT_MAX_RETRIES, DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT_SECONDS
from ..distribution import RarityDistribution
from ..lock_manager import acquire_output_lock
from ..models import BaseWordRow, ResolvedEndpoint, RunBaseline, RunCsvRow
from ..run_csv_repository import RunCsvRepository
from ..step2_metrics import Step2Metrics
from ..support import sanitize_run_slug
from ..lm.client import LmStudioClient, ScoringContext


@dataclass(frozen=True)
class Step2Options:
    run_slug: str
    model: str
    base_csv_path: Path
    output_csv_path: Path
    input_csv_path: Path | None = None
    batch_size: int = DEFAULT_BATCH_SIZE
    limit: int | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_tokens: int = DEFAULT_MAX_TOKENS
    skip_preflight: bool = False
    force: bool = False
    endpoint_option: str | None = None
    base_url_option: str | None = None
    system_prompt: str = ""
    user_template: str = ""


@dataclass(frozen=True)
class Step2Files:
    run_log_path: Path
    failed_log_path: Path
    state_path: Path


@dataclass(frozen=True)
class Step2Context:
    pending: list[BaseWordRow]
    existing_rows: dict[int, RunCsvRow]
    baseline_count: int
    baseline_min_id: int | None
    baseline_max_id: int | None


@dataclass(frozen=True)
class Step2Counters:
    scored_count: int
    failed_count: int


def run_step2(options: Step2Options, *, repo: RunCsvRepository, lm_client: LmStudioClient, output_dir: Path) -> None:
    run_slug = sanitize_run_slug(options.run_slug)
    files = _prepare_files(output_dir, run_slug)
    metrics = lm_client.metrics

    with acquire_output_lock(options.output_csv_path):
        _write_state(files.state_path, _running_state(options))
        try:
            ctx = _build_context(options, repo)
            if not ctx.pending:
                _handle_no_pending(run_slug, files.state_path, options.output_csv_path)
                return

            resolved_endpoint = _resolve_endpoint(options, lm_client)
            counters = _score_pending_batches(options, run_slug, ctx, files, resolved_endpoint, repo, lm_client, metrics)
            pending_after = counters.failed_count

            baseline = RunBaseline(
                count=ctx.baseline_count,
                min_id=ctx.baseline_min_id,
                max_id=ctx.baseline_max_id,
            )
            repo.merge_and_rewrite_atomic(
                path=options.output_csv_path,
                in_memory_rows=list(ctx.existing_rows.values()),
                baseline=baseline,
            )

            _write_state(files.state_path, _completed_state(options, files, counters, pending_after))
            _print_summary(options, files, counters, pending_after, metrics)
        except Exception as exc:
            _write_state(files.state_path, _failed_state(run_slug, exc))
            raise


def _prepare_files(output_dir: Path, run_slug: str) -> Step2Files:
    runs_dir = output_dir / "runs"
    failed_dir = output_dir / "failed_batches"
    runs_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    return Step2Files(
        run_log_path=runs_dir / f"{run_slug}.jsonl",
        failed_log_path=failed_dir / f"{run_slug}.failed.jsonl",
        state_path=runs_dir / f"{run_slug}.state.json",
    )


def _build_context(options: Step2Options, repo: RunCsvRepository) -> Step2Context:
    source_csv = options.input_csv_path or options.base_csv_path
    base_rows = sorted({r.word_id: r for r in repo.load_base_rows(source_csv)}.values(), key=lambda r: r.word_id)
    existing_rows = {r.word_id: r for r in repo.load_run_rows(options.output_csv_path)}

    pending = [row for row in base_rows if options.force or row.word_id not in existing_rows]
    if options.limit and options.limit > 0:
        pending = pending[: options.limit]

    baseline = repo.compute_baseline(list(existing_rows.values()))
    return Step2Context(
        pending=pending,
        existing_rows=existing_rows,
        baseline_count=baseline.count,
        baseline_min_id=baseline.min_id,
        baseline_max_id=baseline.max_id,
    )


def _resolve_endpoint(options: Step2Options, lm_client: LmStudioClient) -> ResolvedEndpoint:
    resolved = lm_client.resolve_endpoint(options.endpoint_option, options.base_url_option)
    print(f"LM endpoint: {resolved.endpoint} (flavor={resolved.flavor.value}, source={resolved.source})")
    if options.skip_preflight:
        print("Skipping LM preflight (--skip-preflight=true)")
    else:
        lm_client.preflight(resolved, options.model)
    return resolved


def _score_pending_batches(
    options: Step2Options,
    run_slug: str,
    ctx: Step2Context,
    files: Step2Files,
    resolved_endpoint: ResolvedEndpoint,
    repo: RunCsvRepository,
    lm_client: LmStudioClient,
    metrics: Step2Metrics | None,
) -> Step2Counters:
    total_pending = len(ctx.pending)
    scored_count = 0
    failed_count = 0
    processed = 0
    distribution = RarityDistribution()
    for row in ctx.existing_rows.values():
        distribution.increment(row.rarity_level)

    min_adaptive = max(5, min(options.batch_size, options.batch_size // 5))
    adapter = BatchSizeAdapter(initial_size=options.batch_size, min_size=min_adaptive)

    scoring_ctx = ScoringContext(
        run_slug=run_slug,
        model=options.model,
        endpoint=resolved_endpoint.endpoint,
        max_retries=options.max_retries,
        timeout_seconds=options.timeout_seconds,
        run_log_path=files.run_log_path,
        failed_log_path=files.failed_log_path,
        system_prompt=options.system_prompt,
        user_template=options.user_template,
        flavor=resolved_endpoint.flavor,
        max_tokens=options.max_tokens,
    )

    remaining = list(ctx.pending)
    while remaining:
        batch_size = min(adapter.recommended_size(), len(remaining))
        batch = remaining[:batch_size]
        del remaining[:batch_size]

        scored = lm_client.score_batch_resilient(batch=batch, context=scoring_ctx)
        adapter.record_outcome(len(scored) / len(batch))
        if metrics:
            metrics.record_batch_result(len(batch), len(scored))

        if scored:
            rows_to_append = _to_run_rows(scored, options.model, run_slug)
            for row in rows_to_append:
                ctx.existing_rows[row.word_id] = row
                distribution.increment(row.rarity_level)
            repo.append_run_rows(options.output_csv_path, rows_to_append)
            scored_count += len(rows_to_append)

        failed_count += len(batch) - len(scored)
        processed += len(batch)
        remaining_count = max(0, total_pending - processed)
        if metrics:
            line = metrics.format_progress(remaining=remaining_count, effective_batch_size=adapter.recommended_size())
            print(f"Step 2 progress run='{run_slug}' {line} {distribution.format()}")
        else:
            print(
                f"Step 2 progress run='{run_slug}' processed={processed}/{total_pending} scored={scored_count} "
                f"failed={failed_count} remaining={remaining_count} {distribution.format()}"
            )

    return Step2Counters(scored_count=scored_count, failed_count=failed_count)


def _to_run_rows(scored: list, model: str, run_slug: str) -> list[RunCsvRow]:
    scored_at = datetime.now(timezone.utc).isoformat()
    return [
        RunCsvRow(
            word_id=s.word_id,
            word=s.word,
            type=s.type,
            rarity_level=s.rarity_level,
            tag=s.tag,
            confidence=s.confidence,
            scored_at=scored_at,
            model=model,
            run_slug=run_slug,
        )
        for s in scored
    ]


def _running_state(options: Step2Options) -> dict[str, object]:
    return {
        "status": "running",
        "run_slug": options.run_slug,
        "model": options.model,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_csv": str(options.base_csv_path.resolve()),
        "input_csv": str(options.input_csv_path.resolve()) if options.input_csv_path else None,
        "output_csv": str(options.output_csv_path.resolve()),
    }


def _completed_state(options: Step2Options, files: Step2Files, counters: Step2Counters, pending_count: int) -> dict[str, object]:
    return {
        "status": "completed",
        "run_slug": options.run_slug,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "scored": counters.scored_count,
        "failed": counters.failed_count,
        "pending": pending_count,
        "output_csv": str(options.output_csv_path.resolve()),
        "run_log": str(files.run_log_path.resolve()),
        "failed_log": str(files.failed_log_path.resolve()),
    }


def _failed_state(run_slug: str, exc: Exception) -> dict[str, object]:
    return {
        "status": "failed",
        "run_slug": run_slug,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "error": str(exc),
    }


def _handle_no_pending(run_slug: str, state_path: Path, output_csv_path: Path) -> None:
    _write_state(
        state_path,
        {
            "status": "completed",
            "run_slug": run_slug,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "scored": 0,
            "failed": 0,
            "pending": 0,
            "message": "No pending words",
        },
    )
    print(f"Step 2 complete. No pending words for run '{run_slug}'.")
    print(f"Run CSV: {output_csv_path}")


def _print_summary(
    options: Step2Options,
    files: Step2Files,
    counters: Step2Counters,
    pending_count: int,
    metrics: Step2Metrics | None,
) -> None:
    if metrics:
        print(metrics.format_summary())
    else:
        print(
            f"Step 2 complete for run '{options.run_slug}': scored={counters.scored_count} failed={counters.failed_count} pending={pending_count}"
        )
    print(f"Run CSV: {options.output_csv_path}")
    print(f"Run log: {files.run_log_path}")
    print(f"Failed log: {files.failed_log_path}")


def _write_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
