# Handover

## What This Project Replaces

This Python project replaces only the rarity/classification tooling. Backend API/runtime apps remain unchanged.

## What Worked

- Strict Step5 `local_id` contract with exact-count enforcement.
- Batch split retries with preserved expected selection counts.
- Gated upload policy based on semantic quality metrics (not histogram only).
- CSV-first workflow with resumable JSONL logs and explicit checkpoints.

## What Did Not Work (and is avoided here)

- Accepting mixed id semantics (`word_id`/`local_id`) in rebalance output.
- Silent parser auto-fill of missing selections.
- Uploading solely because counts matched target distribution.

## Do / Don’t

Do:

- Keep rebalance prompts strict and schema-driven.
- Gate every upload with Jaccard + anchor metrics.
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
