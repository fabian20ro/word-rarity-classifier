# Runbook

## 1) Environment

Required DB env vars:

- `SUPABASE_DB_URL`
- `SUPABASE_DB_USER`
- `SUPABASE_DB_PASSWORD`

Optional LM vars:

- `LMSTUDIO_API_URL` (full endpoint)
- `LMSTUDIO_BASE_URL` (default `http://127.0.0.1:1234`)
- `LMSTUDIO_API_KEY`

## 2) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 3) Base Export

```bash
classificator step1-export --output-csv build/rarity/step1_words.csv
```

## 4) Score Run (Step2)

```bash
classificator step2-score \
  --run campaign_a \
  --model openai/gpt-oss-20b \
  --base-csv build/rarity/step1_words.csv \
  --output-csv build/rarity/runs/campaign_a.csv \
  --batch-size 50 \
  --max-tokens 8000 \
  --timeout-seconds 120 \
  --max-retries 2 \
  --system-prompt-file prompts/system_prompt_ro.txt \
  --user-template-file prompts/user_prompt_template_ro.txt
```

Resume same run:

```bash
classificator step2-score ... --run campaign_a --output-csv build/rarity/runs/campaign_a.csv
```

## 5) Compare Multiple Runs (Step3)

```bash
classificator step3-compare \
  --run-a-csv build/rarity/runs/campaign_a.csv \
  --run-b-csv build/rarity/runs/campaign_b.csv \
  --run-c-csv build/rarity/runs/campaign_c.csv \
  --output-csv build/rarity/step3_comparison.csv \
  --outliers-csv build/rarity/step3_outliers.csv \
  --merge-strategy any-extremes
```

## 6) Optional Rebalance (Step5)

Single transition:

```bash
classificator step5-rebalance \
  --run rb_l2_to_l1 \
  --model openai/gpt-oss-20b \
  --input-csv build/rarity/runs/campaign_a.csv \
  --output-csv build/rarity/runs/campaign_a.rebalanced.csv \
  --from-level 2 --to-level 1 \
  --batch-size 600 --lower-ratio 0.3333
```

Transition list:

```bash
classificator step5-rebalance \
  --run rb_multi \
  --model openai/gpt-oss-20b \
  --input-csv build/rarity/runs/campaign_a.csv \
  --output-csv build/rarity/runs/campaign_a.rebalanced.csv \
  --transitions "2:1,3:2,4:3"
```

## 7) Quality Gate (Mandatory Before Upload)

```bash
classificator quality-audit \
  --candidate-csv build/rarity/runs/campaign_a.rebalanced.csv \
  --reference-csv build/rarity/runs/reference.csv \
  --anchor-l1-file docs/rarity-anchor-l1-ro.txt \
  --min-l1-jaccard 0.80 \
  --min-anchor-l1-precision 0.90 \
  --min-anchor-l1-recall 0.70
```

If this fails, do **not** upload.

## 8) Upload (Step4)

Partial mode (default):

```bash
classificator step4-upload --final-csv build/rarity/runs/campaign_a.rebalanced.csv
```

Full fallback mode (use sparingly):

```bash
classificator step4-upload --final-csv build/rarity/runs/campaign_a.rebalanced.csv --mode full-fallback
```

## 9) Utilities

Retry input from failed JSONL:

```bash
classificator build-retry-input \
  --failed-jsonl build/rarity/failed_batches/campaign_a.failed.jsonl \
  --base-csv build/rarity/step1_words.csv \
  --output-csv build/rarity/retry_inputs/campaign_a_retry.csv
```

Chained fixed-target rebalance (8-step schedule):

```bash
classificator chain-rebalance-target-dist \
  --input-csv build/rarity/runs/campaign_a.csv \
  --model openai/gpt-oss-20b \
  --run-base targetdist_v1 \
  --reference-csv build/rarity/runs/reference.csv \
  --anchor-l1-file docs/rarity-anchor-l1-ro.txt \
  --min-l1-jaccard 0.80 \
  --min-anchor-l1-precision 0.90
```
