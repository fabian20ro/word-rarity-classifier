# AGENTS.md

Operating guide for contributors working in this standalone rarity-classification project.

## Mission

Maintain a reliable Romanian lexical rarity pipeline that:
- reads source words from Supabase PostgreSQL,
- classifies/rebalances with local LLMs using strict JSON contracts,
- writes reproducible intermediary CSV/JSONL artifacts,
- uploads validated levels back to Supabase only after quality gates pass.

## Core Rules

1. Step5 selection contract is strict.
- LM output must be exact-count local ids (`1..N`, no duplicates, no `0`).
- Never reintroduce silent auto-fill of missing selections.

2. Upload gating is mandatory.
- Pre-upload candidate must be checked with Jaccard and anchor precision/recall.
- Do not upload based only on histogram fit.

3. CSV-first operation.
- Keep all step artifacts explicit and resumable.
- Avoid hidden in-memory-only workflows.

4. Upload mode default is `partial`.
- Use `full-fallback` only with explicit intent.

## Quick Commands

- Step1 export: `classificator step1-export --output-csv build/rarity/step1_words.csv`
- Step2 score: `classificator step2-score ...`
- Step3 compare: `classificator step3-compare ...`
- Step5 rebalance: `classificator step5-rebalance ...`
- Quality gate: `classificator quality-audit ...`
- Step4 upload: `classificator step4-upload --final-csv <candidate.csv>`

## File Map

- CLI: `src/classificator/cli.py`
- LM client/parser: `src/classificator/lm/`
- Step modules: `src/classificator/steps/`
- Tooling: `src/classificator/tools/`
- Runbook: `docs/RUNBOOK.md`
- Handover and guardrails: `docs/HANDOVER.md`

## Testing Expectations

Before handoff:
- run unit tests (`python -m unittest discover -s tests -p 'test_*.py'`),
- run at least one quality-audit smoke command,
- if LM/DB behavior changed, include an operator note in docs.
