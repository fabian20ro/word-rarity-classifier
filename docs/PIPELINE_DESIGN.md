# Pipeline Design

## Goal

Classify Romanian lexical rarity (`1..5`) with robust offline orchestration:

- deterministic intermediate files,
- resumable LM batch processing,
- strict rebalance contracts,
- gated uploads (Jaccard + anchor precision/recall).

## Repository Boundary

This repository is the source of truth for offline rarity classification.
`fabian20ro/propozitii-nostime` consumes `words.rarity_level` at runtime, but does not host classifier runtime code, prompts, or orchestration.

## Why Python

- Better data tooling for batch CSV analysis and audits.
- Faster iteration on parser/repair heuristics and experiment scripts.
- Easier standalone extraction as a dedicated classification repo.

## Implementation Shape

- Python CLI + modular pipeline steps.
- CSV-first and resumable execution.
- Strict parser/schema enforcement around LM JSON.
- Rebalance transitions with checkpoints and recoverable state.
- Prompt assets + quality-audit tooling + optional chained rebalance helper.

## Step Model

- `step1-export`: DB -> `step1_words.csv` (`word_id,word,type`).
- `step2-score`: LM scores full list into run CSV (`rarity_level`, `tag`, `confidence`) with:
  - append-resume behavior,
  - lock file (`.lock`),
  - guarded final rewrite,
  - adaptive batch size,
  - run/failure JSONL logs.
- `step3-compare`: merges 2/3 runs into `final_level` and outliers.
- `step4-upload`: writes `final_level`/`rarity_level` to DB (default partial mode) and writes upload markers.
- `step5-rebalance`: strict two-bucket split from source levels to target level using `local_id` selections only.

## Rebalance Contract (Critical)

- LM must return exactly `N` selected ids per batch.
- Id domain is strictly local batch ids (`1..batch_size`), unique, no `0`.
- Parser fails fast when count mismatches (no silent auto-fill).
- Recursive split retries preserve expected selection counts proportionally.

## Quality Gate Contract

Before upload, candidate CSV must pass:

- L1 Jaccard against trusted reference run (`word_id` set overlap stability),
- L1 anchor precision/recall from curated Romanian base vocabulary anchors.

This protects against superficially correct histograms with semantically poor L1 content.

## Data Contracts

- Level semantics: lower number means more common word.
- Output values are constrained to `1..5`.
- Step5 selection mode uses local batch ids only (`1..N`, unique, exact count, no `0`).
- Step4 upload default mode is `partial`.

## Artifact Layout

- `build/rarity/runs/*.csv` step2/step5 outputs
- `build/rarity/runs/*.jsonl` step2 raw LM logs
- `build/rarity/failed_batches/*.failed.jsonl` step2 unresolved failures
- `build/rarity/rebalance/**` step5 runs/failures/checkpoints/switched words
- `build/rarity/step4_upload_report.csv`

## Known Tradeoffs

- Step2 and Step5 are single-process orchestrations (not distributed workers).
- Quality anchors start as seed set; precision improves with larger curated anchors.
- Local LM behavior varies by model; strict parser/schema catches drift but may increase retries.
