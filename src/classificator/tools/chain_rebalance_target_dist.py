from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..constants import DEFAULT_REBALANCE_BATCH_SIZE
from ..lm.client import LmStudioClient
from ..run_csv_repository import RunCsvRepository
from ..steps.step5_rebalance import Step5Options, run_step5
from ..tools.quality_audit import run_quality_audit
from ..transitions import LevelTransition


@dataclass(frozen=True)
class ChainOptions:
    input_csv: Path
    model: str
    run_base: str
    runs_dir: Path
    state_file: Path
    resume: bool
    final_output_csv: Path | None
    batch_size: int
    max_tokens: int
    timeout_seconds: int
    max_retries: int
    system_prompt_file: Path
    user_template_file: Path
    reference_csv: Path | None
    anchor_l1_file: Path | None
    min_l1_jaccard: float | None
    min_anchor_l1_precision: float | None
    min_anchor_l1_recall: float | None
    endpoint_option: str | None
    base_url_option: str | None


def run_chain_rebalance(*, options: ChainOptions, repo: RunCsvRepository, lm_client: LmStudioClient, output_dir: Path) -> Path:
    if not options.input_csv.exists():
        raise FileNotFoundError(f"Missing input CSV: {options.input_csv}")

    transitions = [
        (1, LevelTransition(from_level=1, from_level_upper=2, to_level=1)),
        (2, LevelTransition(from_level=1, from_level_upper=2, to_level=1)),
        (3, LevelTransition(from_level=1, from_level_upper=2, to_level=1)),
        (4, LevelTransition(from_level=2, from_level_upper=3, to_level=2)),
        (5, LevelTransition(from_level=2, from_level_upper=3, to_level=2)),
        (6, LevelTransition(from_level=3, from_level_upper=4, to_level=3)),
        (7, LevelTransition(from_level=3, from_level_upper=4, to_level=3)),
        (8, LevelTransition(from_level=4, from_level_upper=5, to_level=4)),
    ]

    current_csv = options.input_csv
    last_completed = 0
    if options.resume and options.state_file.exists():
        st = _load_state(options.state_file)
        last_completed = st["last_completed_step"]
        current_csv = Path(st["current_csv"])
        if not current_csv.exists():
            raise FileNotFoundError(f"State file points to missing CSV: {current_csv}")
    elif options.resume:
        for step_idx, _ in transitions:
            candidate = options.runs_dir / f"{options.run_base}_step{step_idx}.csv"
            if candidate.exists():
                current_csv = candidate
                last_completed = step_idx
            else:
                break

    options.runs_dir.mkdir(parents=True, exist_ok=True)
    total_words = _count_total_words(current_csv, repo)
    target_l1 = 2500
    target_l2 = 7500
    target_l3 = 15000
    target_l5 = 30000
    target_l4 = total_words - target_l1 - target_l2 - target_l3 - target_l5
    if target_l4 < 1:
        raise ValueError(f"Invalid target distribution for total={total_words}: computed level4={target_l4}")
    targets = {1: target_l1, 2: target_l2, 3: target_l3, 4: target_l4, 5: target_l5}

    print("Starting chained rarity rebalancing campaign")
    print(f"model={options.model}")
    print(f"run_base={options.run_base}")
    print(f"resume={options.resume} state_file={options.state_file} last_completed_step={last_completed}")
    print(
        f"batch_size={options.batch_size} max_tokens={options.max_tokens} timeout_seconds={options.timeout_seconds} max_retries={options.max_retries}"
    )
    print(f"current_csv={current_csv}")
    print(f"target_distribution=[1:{target_l1} 2:{target_l2} 3:{target_l3} 4:{target_l4} 5:{target_l5}] total={total_words}")

    system_prompt = options.system_prompt_file.read_text(encoding="utf-8")
    user_prompt = options.user_template_file.read_text(encoding="utf-8")

    for step_idx, transition in transitions:
        next_csv = options.runs_dir / f"{options.run_base}_step{step_idx}.csv"
        if options.resume and step_idx <= last_completed:
            if not next_csv.exists():
                raise FileNotFoundError(f"Resume state says step completed, but output missing: {next_csv}")
            current_csv = next_csv
            print(f"[step {step_idx}] resume skip -> {current_csv}")
            continue

        from_low = transition.from_level
        from_high = transition.from_level_upper or transition.from_level
        to_level = transition.to_level
        count_low = _get_level_count(current_csv, from_low, repo)
        count_high = _get_level_count(current_csv, from_high, repo)
        pool = count_low + count_high
        target_to_level = targets[to_level]

        if pool <= 1:
            raise ValueError(f"[step {step_idx}] pool too small for levels {from_low}+{from_high}: {pool}")
        if target_to_level < 1 or target_to_level >= pool:
            raise ValueError(
                f"[step {step_idx}] invalid target={target_to_level} for pool={pool} (levels {from_low}+{from_high})"
            )

        ratio = target_to_level / pool
        if not (0.01 <= ratio <= 0.99):
            raise ValueError(f"[step {step_idx}] ratio out of range 0.01..0.99: ratio={ratio}")

        step_slug = _sanitize_slug(f"s{step_idx}_{from_low}{from_high}to{to_level}_{options.run_base[-24:]}")

        print(f"\n========== STEP {step_idx} ==========")
        print(f"input_csv={current_csv}")
        print(f"output_csv={next_csv}")
        print(f"run_slug={step_slug}")
        print(f"transition={from_low}-{from_high}->{to_level}")
        print(f"pool={pool} (l{from_low}={count_low}, l{from_high}={count_high})")
        print(f"target_l{to_level}={target_to_level} ratio={ratio:.12f}")

        run_step5(
            Step5Options(
                run_slug=step_slug,
                model=options.model,
                input_csv_path=current_csv,
                output_csv_path=next_csv,
                batch_size=options.batch_size,
                lower_ratio=ratio,
                max_retries=options.max_retries,
                timeout_seconds=options.timeout_seconds,
                max_tokens=options.max_tokens,
                skip_preflight=False,
                endpoint_option=options.endpoint_option,
                base_url_option=options.base_url_option,
                transitions=[transition],
                system_prompt=system_prompt,
                user_template=user_prompt,
            ),
            repo=repo,
            lm_client=lm_client,
            output_dir=output_dir,
        )

        current_csv = next_csv
        _write_state(options.state_file, step_idx, current_csv, options)

    if options.final_output_csv is not None:
        options.final_output_csv.parent.mkdir(parents=True, exist_ok=True)
        options.final_output_csv.write_bytes(current_csv.read_bytes())
        print(f"Final output copied to: {options.final_output_csv}")
    else:
        print(f"Final output CSV: {current_csv}")

    _write_state(options.state_file, 8, current_csv, options)

    if options.reference_csv or options.anchor_l1_file:
        result = run_quality_audit(
            candidate_csv=current_csv,
            reference_csv=options.reference_csv,
            anchor_l1_file=options.anchor_l1_file,
            min_l1_jaccard=options.min_l1_jaccard,
            min_anchor_l1_precision=options.min_anchor_l1_precision,
            min_anchor_l1_recall=options.min_anchor_l1_recall,
            repo=repo,
        )
        if not result.passed:
            raise RuntimeError("Quality audit failed")

    return current_csv


def _count_total_words(csv_path: Path, repo: RunCsvRepository) -> int:
    table = repo.read_table(csv_path)
    return len(table.records)


def _get_level_count(csv_path: Path, level: int, repo: RunCsvRepository) -> int:
    table = repo.read_table(csv_path)
    if "final_level" in table.headers:
        col = "final_level"
    elif "rarity_level" in table.headers:
        col = "rarity_level"
    else:
        raise ValueError("CSV must contain final_level or rarity_level")
    idx = table.headers.index(col)
    count = 0
    for rec in table.records:
        try:
            if int(rec.values[idx]) == level:
                count += 1
        except Exception:
            continue
    return count


def _write_state(path: Path, step: int, current_csv: Path, options: ChainOptions) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"last_completed_step\t{step}",
        f"current_csv\t{current_csv}",
        f"run_base\t{options.run_base}",
        f"model\t{options.model}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_state(path: Path) -> dict[str, object]:
    payload: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "\t" not in raw:
            continue
        k, v = raw.split("\t", 1)
        payload[k] = v
    if "last_completed_step" not in payload or "current_csv" not in payload:
        raise ValueError(f"Invalid state file: {path}")
    return {
        "last_completed_step": int(payload["last_completed_step"]),
        "current_csv": payload["current_csv"],
    }


def _sanitize_slug(raw: str) -> str:
    cleaned = "".join(ch for ch in raw.lower().replace("-", "_") if ch.isalnum() or ch == "_")
    cleaned = cleaned[:40]
    return cleaned or "rebalance_run"
