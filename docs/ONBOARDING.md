# Onboarding

## First 20 Minutes

1. Read `README.md` and `AGENTS.md`.
2. Read `docs/PIPELINE_DESIGN.md` and `docs/RUNBOOK.md`.
3. Internalize integration boundary: this repo owns classifier runtime; `propozitii-nostime` only consumes `words.rarity_level`.
4. Install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

5. Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```

## First Safe Validation Flow

1. Export a small source CSV with `step1-export`.
2. Run `quality-audit` on a tiny synthetic CSV to confirm tooling works.
3. Run one short Step2 scoring test on limited rows.
4. Verify logs (`runs/*.jsonl`, `failed_batches/*.failed.jsonl`).

## Critical Don'ts

- Don’t relax strict Step5 local-id contract checks.
- Don’t upload without quality gate pass.
- Don’t treat target histogram match as semantic quality proof.
