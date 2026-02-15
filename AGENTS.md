# AGENTS.md

Operating guide for contributors working in this standalone rarity-classification project.

## Mission

Maintain a reliable Romanian lexical rarity pipeline that:
- reads source words from Supabase PostgreSQL,
- classifies/rebalances with local LLMs using strict JSON contracts,
- writes reproducible intermediary CSV/JSONL artifacts,
- uploads validated levels back to Supabase only after quality gates pass.

## Memory & Continuous Learning

This project maintains a persistent learning system across AI agent sessions.

### Required Workflow

1. **Start of task:** Read `LESSONS_LEARNED.md` before writing any code
2. **During work:** Note any surprises, gotchas, or non-obvious discoveries
3. **End of iteration:** Append to `ITERATION_LOG.md` with what happened
4. **End of iteration:** If the insight is reusable and validated, also add to `LESSONS_LEARNED.md`
5. **Pattern detection:** If the same issue appears 2+ times in the log, promote it to a lesson

### Files

| File | Purpose | When to Write |
|------|---------|---------------|
| `LESSONS_LEARNED.md` | Curated, validated, reusable wisdom | End of iteration (if insight is reusable) |
| `ITERATION_LOG.md` | Raw session journal, append-only | End of every iteration (always) |

### Rules

- Never delete entries from `ITERATION_LOG.md` — it's append-only
- In `LESSONS_LEARNED.md`, obsolete lessons go to the Archive section, not deleted
- Keep entries concise — a future agent scanning 100 entries needs signal, not prose
- Date-stamp everything in `YYYY-MM-DD` format
- When in doubt about whether something is worth logging: log it

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
- Distribution check: `classificator rarity-distribution --csv <run.csv>`
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
