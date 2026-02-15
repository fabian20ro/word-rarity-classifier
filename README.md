# classificator

Standalone Python reimplementation of the Romanian rarity classification pipeline.

This repository is the active home of the offline rarity-classification system previously hosted inside `fabian20ro/propozitii-nostime`.
It reads words from Supabase PostgreSQL, writes intermediary CSV/JSONL artifacts, runs LM scoring/rebalancing, and uploads final levels back to Supabase.

## Integration Boundary

Downstream app `fabian20ro/propozitii-nostime` does not run classifier steps at runtime.
It only consumes `words.rarity_level` via `minRarity`/`rarity` query parameters.

Contract this repository must preserve:

- `rarity_level` stays in `1..5`
- lower number means more common word
- uploads are explicit and auditable

## What It Includes

- Step A: export words from DB to CSV (`word_id,word,type`)
- Step B: LM scoring to `rarity_level` CSV (resume-friendly, append + guarded rewrite)
- Step C: multi-run comparator and outlier report (`final_level`)
- Step D: upload final levels to DB (`partial` default) + upload markers
- Step E: rebalance from one/two source levels to target level with strict local-id selection
- Quality audit: L1 Jaccard + anchor-set precision/recall gates
- Rarity distribution utility for any run/comparison CSV
- Retry input builder from failed JSONL
- Chained target-distribution rebalancer with built-in quality gate

## Data Contracts

- Level semantics: lower number = more common.
- Output levels are constrained to `1..5`.
- Step5 selection ids are batch-local (`local_id` in `1..N`), unique, exact count, no `0`.
- Upload mode default is `partial`; use `full-fallback` only intentionally.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Environment

For DB access (preferred):

- `SUPABASE_DB_URL` e.g. `postgresql://...`
- `SUPABASE_DB_USER`
- `SUPABASE_DB_PASSWORD`

For LM endpoint:

- `LMSTUDIO_API_URL` full endpoint (optional)
- `LMSTUDIO_BASE_URL` base URL, default `http://127.0.0.1:1234`
- `LMSTUDIO_API_KEY` optional bearer token

## Quickstart

```bash
# A) Export words
classificator step1-export --output-csv build/rarity/step1_words.csv

# B) Score with LM
classificator step2-score \
  --run campaign_a \
  --model openai/gpt-oss-20b \
  --base-csv build/rarity/step1_words.csv \
  --output-csv build/rarity/runs/campaign_a.csv \
  --system-prompt-file prompts/system_prompt_ro.txt \
  --user-template-file prompts/user_prompt_template_ro.txt

# E) Optional rebalance
classificator step5-rebalance \
  --run rb_a \
  --model openai/gpt-oss-20b \
  --input-csv build/rarity/runs/campaign_a.csv \
  --output-csv build/rarity/runs/campaign_a.rebalanced.csv \
  --from-level 2 --to-level 1

# Quality gate
classificator quality-audit \
  --candidate-csv build/rarity/runs/campaign_a.rebalanced.csv \
  --reference-csv build/rarity/runs/reference.csv \
  --anchor-l1-file docs/rarity-anchor-l1-ro.txt \
  --min-l1-jaccard 0.80 \
  --min-anchor-l1-precision 0.90

# Distribution check
classificator rarity-distribution --csv build/rarity/runs/campaign_a.rebalanced.csv

# D) Upload to DB (partial default)
classificator step4-upload --final-csv build/rarity/runs/campaign_a.rebalanced.csv
```

## Docs

- `AGENTS.md` contributor operating guide
- `docs/ONBOARDING.md` first-hour checklist
- `docs/RUNBOOK.md` execution guide
- `docs/PIPELINE_DESIGN.md` design decisions and why
- `docs/HANDOVER.md` operator handover (do/don't + troubleshooting)
- `LESSONS_LEARNED.md` historical pitfalls and safeguards
- `docs/rarity-anchor-l1-ro.txt` seed L1 anchor set

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```
