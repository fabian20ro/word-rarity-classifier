# Handover

## What This Project Replaces

This Python project replaces only the rarity/classification tooling. Backend API/runtime apps remain unchanged.

`fabian20ro/propozitii-nostime` is a consumer of DB rarity output only (`words.rarity_level` via `minRarity`/`rarity` filters). Classifier orchestration, prompts, and audits live in this repository.

## Non-Negotiable Contracts

- Output rarity levels stay in `1..5` with lower level = more common word.
- Step5 rebalance selections use only batch-local ids (`1..N`), no duplicates, no `0`, exact count.
- Upload must stay gated by both:
  - L1 set stability (Jaccard vs reference),
  - L1 anchor precision/recall.
- Upload mode default is `partial`; `full-fallback` is explicit exception mode.

## What Worked

- Strict Step5 `local_id` contract with exact-count enforcement.
- Batch split retries with preserved expected selection counts.
- Gated upload policy based on semantic quality metrics (not histogram only).
- CSV-first workflow with resumable JSONL logs and explicit checkpoints.
- Deterministic decoding profiles (`temperature=0`) for stable structured output.
- Stratified source mixing improves pair-level rebalance stability.

## What Did Not Work (and is avoided here)

- Accepting mixed id semantics (`word_id`/`local_id`) in rebalance output.
- Silent parser auto-fill of missing selections.
- Uploading solely because counts matched target distribution.
- Treating small anchor lists as sufficient long-term quality protection.

## Do / Don’t

Do:

- Keep rebalance prompts strict and schema-driven.
- Gate every upload with Jaccard + anchor metrics.
- Run low-confidence L1 human review regularly (`review-low-confidence` + `l1-review-check`).
- Expand anchor list over time (target >= 400 curated L1 words).
- Preserve partial upload default during iteration.

Don’t:

- Relax Step5 selection count checks.
- Re-enable permissive fallback that invents/auto-fills ids.
- Run `full-fallback` uploads during experiments unless explicitly intended.

## Suggested Baseline Run Flow

1. `step1-export`
2. one or more `step2-score` runs
3. optional `step3-compare`
4. optional `step5-rebalance`
5. `quality-audit` (must pass)
6. `step4-upload`

## Troubleshooting

- Frequent malformed LM output:
  - reduce `--batch-size`,
  - keep `temperature=0` model profiles,
  - use retry input builder for unresolved words.

- Rebalance count mismatch errors:
  - verify prompt files unchanged,
  - ensure model supports strict JSON output,
  - avoid manually editing rebalance local-id input shape.

- Low anchor precision:
  - check candidate L1 words manually,
  - tighten prompt instructions,
  - rerun targeted rebalance on levels `1+2 -> 1`.

## Handoff Checklist for Next Operator

- Confirm DB credentials and LM endpoint reachability.
- Confirm prompt files used in command are the intended ones.
- Confirm quality thresholds used for this campaign.
- Confirm upload mode is `partial` unless approved otherwise.
- Archive run command lines and generated artifacts paths.
