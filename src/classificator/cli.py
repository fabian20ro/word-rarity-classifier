from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_OUTLIER_THRESHOLD,
    DEFAULT_REBALANCE_BATCH_SIZE,
    DEFAULT_REBALANCE_LOWER_RATIO,
    DEFAULT_REBALANCE_TRANSITIONS,
    DEFAULT_TIMEOUT_SECONDS,
    ensure_output_dir,
)
from .lm.client import LmStudioClient
from .run_csv_repository import RunCsvRepository
from .step2_metrics import Step2Metrics
from .steps.step1_export import Step1Options, run_step1
from .steps.step2_score import Step2Options, run_step2
from .steps.step3_compare import Step3Options, run_step3
from .steps.step4_upload import Step4Options, run_step4
from .steps.step5_rebalance import Step5Options, run_step5
from .tools.build_retry_input import build_retry_input
from .tools.chain_rebalance_target_dist import ChainOptions, run_chain_rebalance
from .tools.quality_audit import run_quality_audit
from .transitions import (
    LevelTransition,
    parse_transitions,
    require_valid_pair_transition,
    require_valid_transition,
    validate_transition_set,
)
from .upload_marker_writer import UploadMarkerWriter
from .word_store import WordStore
from .models import Step3MergeStrategy, UploadMode


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    output_dir = ensure_output_dir(Path(args.output_dir) if getattr(args, "output_dir", None) else None)
    repo = RunCsvRepository()

    if args.command in {"step1-export", "step1"}:
        store = WordStore()
        run_step1(Step1Options(output_csv_path=Path(args.output_csv)), word_store=store, repo=repo)
        return 0

    if args.command in {"step2-score", "step2"}:
        metrics = Step2Metrics()
        lm_client = LmStudioClient(api_key=os.getenv("LMSTUDIO_API_KEY"), metrics=metrics)
        run_step2(
            Step2Options(
                run_slug=args.run,
                model=args.model,
                base_csv_path=Path(args.base_csv),
                output_csv_path=Path(args.output_csv),
                input_csv_path=Path(args.input) if args.input else None,
                batch_size=args.batch_size,
                limit=args.limit,
                max_retries=args.max_retries,
                timeout_seconds=args.timeout_seconds,
                max_tokens=args.max_tokens,
                skip_preflight=args.skip_preflight,
                force=args.force,
                endpoint_option=args.endpoint,
                base_url_option=args.base_url,
                system_prompt=Path(args.system_prompt_file).read_text(encoding="utf-8").strip(),
                user_template=Path(args.user_template_file).read_text(encoding="utf-8").strip(),
            ),
            repo=repo,
            lm_client=lm_client,
            output_dir=output_dir,
        )
        return 0

    if args.command in {"step3-compare", "step3"}:
        run_step3(
            Step3Options(
                run_a_csv_path=Path(args.run_a_csv),
                run_b_csv_path=Path(args.run_b_csv),
                run_c_csv_path=Path(args.run_c_csv) if args.run_c_csv else None,
                output_csv_path=Path(args.output_csv),
                outliers_csv_path=Path(args.outliers_csv),
                base_csv_path=Path(args.base_csv),
                outlier_threshold=args.outlier_threshold,
                confidence_threshold=args.confidence_threshold,
                merge_strategy=Step3MergeStrategy.parse(args.merge_strategy),
            ),
            repo=repo,
        )
        return 0

    if args.command in {"step4-upload", "step4"}:
        store = WordStore()
        marker = UploadMarkerWriter(repo)
        run_step4(
            Step4Options(
                final_csv_path=Path(args.final_csv),
                mode=UploadMode.parse(args.mode),
                report_path=Path(args.report_csv),
                upload_batch_id=args.upload_batch_id,
            ),
            word_store=store,
            repo=repo,
            marker_writer=marker,
        )
        return 0

    if args.command in {"step5-rebalance", "step5"}:
        metrics = Step2Metrics()
        lm_client = LmStudioClient(api_key=os.getenv("LMSTUDIO_API_KEY"), metrics=metrics)
        transitions = _resolve_step5_transitions(args)
        run_step5(
            Step5Options(
                run_slug=args.run,
                model=args.model,
                input_csv_path=Path(args.input_csv),
                output_csv_path=Path(args.output_csv),
                batch_size=args.batch_size,
                lower_ratio=args.lower_ratio,
                max_retries=args.max_retries,
                timeout_seconds=args.timeout_seconds,
                max_tokens=args.max_tokens,
                skip_preflight=args.skip_preflight,
                endpoint_option=args.endpoint,
                base_url_option=args.base_url,
                seed=args.seed,
                transitions=transitions,
                system_prompt=Path(args.system_prompt_file).read_text(encoding="utf-8").strip(),
                user_template=Path(args.user_template_file).read_text(encoding="utf-8").strip(),
            ),
            repo=repo,
            lm_client=lm_client,
            output_dir=output_dir,
        )
        return 0

    if args.command == "quality-audit":
        result = run_quality_audit(
            candidate_csv=Path(args.candidate_csv),
            reference_csv=Path(args.reference_csv) if args.reference_csv else None,
            anchor_l1_file=Path(args.anchor_l1_file) if args.anchor_l1_file else None,
            min_l1_jaccard=args.min_l1_jaccard,
            min_anchor_l1_precision=args.min_anchor_l1_precision,
            min_anchor_l1_recall=args.min_anchor_l1_recall,
            repo=repo,
        )
        return 0 if result.passed else 1

    if args.command == "build-retry-input":
        rows = build_retry_input(
            failed_jsonl=Path(args.failed_jsonl),
            base_csv=Path(args.base_csv),
            output_csv=Path(args.output_csv),
            repo=repo,
        )
        print(f"Wrote retry input CSV: {args.output_csv} (rows={rows})")
        return 0

    if args.command == "chain-rebalance-target-dist":
        metrics = Step2Metrics()
        lm_client = LmStudioClient(api_key=os.getenv("LMSTUDIO_API_KEY"), metrics=metrics)
        run_chain_rebalance(
            options=ChainOptions(
                input_csv=Path(args.input_csv),
                model=args.model,
                run_base=args.run_base,
                runs_dir=Path(args.runs_dir),
                state_file=Path(args.state_file) if args.state_file else Path(args.runs_dir) / f"{args.run_base}.rebalance.state",
                resume=args.resume,
                final_output_csv=Path(args.final_output_csv) if args.final_output_csv else None,
                batch_size=args.batch_size,
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
                system_prompt_file=Path(args.system_prompt_file),
                user_template_file=Path(args.user_template_file),
                reference_csv=Path(args.reference_csv) if args.reference_csv else None,
                anchor_l1_file=Path(args.anchor_l1_file) if args.anchor_l1_file else None,
                min_l1_jaccard=args.min_l1_jaccard,
                min_anchor_l1_precision=args.min_anchor_l1_precision,
                min_anchor_l1_recall=args.min_anchor_l1_recall,
                endpoint_option=args.endpoint,
                base_url_option=args.base_url,
            ),
            repo=repo,
            lm_client=lm_client,
            output_dir=output_dir,
        )
        return 0

    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="classificator", description="Romanian rarity classificator pipeline")
    parser.add_argument("--output-dir", default="build/rarity", help="Output root dir (default: build/rarity)")

    sub = parser.add_subparsers(dest="command")

    p1 = sub.add_parser("step1-export", help="Export source words from DB to CSV")
    p1.add_argument("--output-csv", required=True)
    sub.add_parser("step1", help="Alias of step1-export").add_argument("--output-csv", required=True)

    p2 = sub.add_parser("step2-score", help="Score words with LM and write run CSV")
    _add_step2_args(p2)
    p2a = sub.add_parser("step2", help="Alias of step2-score")
    _add_step2_args(p2a)

    p3 = sub.add_parser("step3-compare", help="Compare 2-3 run CSVs and produce final_level")
    _add_step3_args(p3)
    p3a = sub.add_parser("step3", help="Alias of step3-compare")
    _add_step3_args(p3a)

    p4 = sub.add_parser("step4-upload", help="Upload final levels to DB")
    _add_step4_args(p4)
    p4a = sub.add_parser("step4", help="Alias of step4-upload")
    _add_step4_args(p4a)

    p5 = sub.add_parser("step5-rebalance", help="Rebalance levels with strict local_id selection")
    _add_step5_args(p5)
    p5a = sub.add_parser("step5", help="Alias of step5-rebalance")
    _add_step5_args(p5a)

    qa = sub.add_parser("quality-audit", help="Compute distribution + L1 Jaccard + anchor precision/recall")
    qa.add_argument("--candidate-csv", required=True)
    qa.add_argument("--reference-csv")
    qa.add_argument("--anchor-l1-file")
    qa.add_argument("--min-l1-jaccard", type=float)
    qa.add_argument("--min-anchor-l1-precision", type=float)
    qa.add_argument("--min-anchor-l1-recall", type=float)

    br = sub.add_parser("build-retry-input", help="Build retry input CSV from failed JSONL")
    br.add_argument("--failed-jsonl", required=True)
    br.add_argument("--base-csv", required=True)
    br.add_argument("--output-csv", required=True)

    ch = sub.add_parser("chain-rebalance-target-dist", help="Run fixed 8-step rebalance chain to target distribution")
    ch.add_argument("--input-csv", required=True)
    ch.add_argument("--model", default="openai/gpt-oss-20b")
    ch.add_argument("--run-base", default="rb_run")
    ch.add_argument("--runs-dir", default="build/rarity/runs")
    ch.add_argument("--state-file")
    ch.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    ch.add_argument("--final-output-csv")
    ch.add_argument("--batch-size", type=int, default=DEFAULT_REBALANCE_BATCH_SIZE)
    ch.add_argument("--max-tokens", type=int, default=1200)
    ch.add_argument("--timeout-seconds", type=int, default=120)
    ch.add_argument("--max-retries", type=int, default=2)
    ch.add_argument("--system-prompt-file", default="prompts/rebalance_system_prompt_ro.txt")
    ch.add_argument("--user-template-file", default="prompts/rebalance_user_prompt_template_ro.txt")
    ch.add_argument("--reference-csv")
    ch.add_argument("--anchor-l1-file")
    ch.add_argument("--min-l1-jaccard", type=float)
    ch.add_argument("--min-anchor-l1-precision", type=float)
    ch.add_argument("--min-anchor-l1-recall", type=float)
    ch.add_argument("--endpoint")
    ch.add_argument("--base-url")

    return parser


def _add_step2_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--input")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--skip-preflight", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--force", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--endpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--system-prompt-file", default="prompts/system_prompt_ro.txt")
    parser.add_argument("--user-template-file", default="prompts/user_prompt_template_ro.txt")


def _add_step3_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-a-csv", required=True)
    parser.add_argument("--run-b-csv", required=True)
    parser.add_argument("--run-c-csv")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--outliers-csv", default="build/rarity/step3_outliers.csv")
    parser.add_argument("--base-csv", default="build/rarity/step1_words.csv")
    parser.add_argument("--outlier-threshold", type=int, default=DEFAULT_OUTLIER_THRESHOLD)
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--merge-strategy", default="median")


def _add_step4_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--final-csv", required=True)
    parser.add_argument("--mode", default="partial")
    parser.add_argument("--report-csv", default="build/rarity/step4_upload_report.csv")
    parser.add_argument("--upload-batch-id")


def _add_step5_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_REBALANCE_BATCH_SIZE)
    parser.add_argument("--lower-ratio", type=float, default=DEFAULT_REBALANCE_LOWER_RATIO)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--skip-preflight", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--endpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--seed", type=int)

    parser.add_argument("--from-level", type=int)
    parser.add_argument("--from-level-high", type=int)
    parser.add_argument("--to-level", type=int)
    parser.add_argument("--transitions", default=DEFAULT_REBALANCE_TRANSITIONS)

    parser.add_argument("--system-prompt-file", default="prompts/rebalance_system_prompt_ro.txt")
    parser.add_argument("--user-template-file", default="prompts/rebalance_user_prompt_template_ro.txt")


def _resolve_step5_transitions(args) -> list[LevelTransition]:
    from_level = args.from_level
    from_level_high = args.from_level_high
    to_level = args.to_level

    if from_level is not None or to_level is not None:
        if from_level is None or to_level is None:
            raise ValueError("Step5 requires both --from-level and --to-level when one is provided")
        if from_level_high is not None:
            require_valid_pair_transition(from_level, from_level_high, to_level)
            transitions = [LevelTransition(from_level=from_level, from_level_upper=from_level_high, to_level=to_level)]
        else:
            require_valid_transition(from_level, to_level)
            transitions = [LevelTransition(from_level=from_level, to_level=to_level)]
    else:
        transitions = parse_transitions(args.transitions)

    validate_transition_set(transitions)
    return transitions


if __name__ == "__main__":
    sys.exit(main())
