# Lessons Learned

> This file is maintained by AI agents working on this project.
> It captures validated, reusable insights discovered during development.
> **Read this file at the start of every task. Update it at the end of every iteration.**

## How to Use This File

### Reading (Start of Every Task)
Before starting any work, read this file to avoid repeating known mistakes
and to leverage proven approaches.

### Writing (End of Every Iteration)
After completing a task or iteration, evaluate whether any new insight was
gained that would be valuable for future sessions. If yes, add it to the
appropriate category below.

### Promotion from Iteration Log
Patterns that appear 2+ times in `ITERATION_LOG.md` should be promoted
here as a validated lesson.

### Pruning
If a lesson becomes obsolete (e.g., a dependency was removed, an API changed),
move it to the Archive section at the bottom with a date and reason.

---

## Architecture & Design Decisions

<!-- Insights about system design, patterns that work/don't work in this codebase -->
<!-- Format: **[YYYY-MM-DD]** Brief title — Explanation -->
**[2026-02-14]** Classifier/consumer boundary must stay explicit — `word-rarity-classifier` owns pipeline runtime and artifacts; downstream apps only consume `words.rarity_level`.
**[2026-02-14]** CSV-first orchestration is a reliability feature — reproducible step artifacts plus checkpoints are required for multi-hour recovery and auditability.

## Code Patterns & Pitfalls

<!-- Language/framework-specific gotchas discovered in this project -->
<!-- Format: **[YYYY-MM-DD]** Brief title — Explanation -->
**[2026-02-14]** Step5 id domain must remain batch-local — selection output must use only `local_id` in `1..N`; mixing in `word_id` or allowing `0` creates silent corruption risk.
**[2026-02-14]** Prompt/parser contract drift causes hard failures — exact-count semantics and id rules must match verbatim between prompt text and parser validation.
**[2026-02-14]** Prompt wording is a behavior contract — small phrasing edits can materially shift L1 composition; treat prompt files as versioned assets.
**[2026-02-14]** Strict parsing beats permissive autofill — long rebalance campaigns are safer when malformed LM selections fail fast instead of being auto-completed.
**[2026-02-14]** Deterministic decode profiles improve JSON stability — lower-variance decoding (for example `temperature=0`) reduces structured-output breakage.
**[2026-02-20]** Reset/reimport can invalidate `word_id` alignment — if Step4 report is all `missing_db_word`, verify DB `id` range before retrying; remap candidate IDs deterministically (for example fixed offset) and keep upload mode `partial` so only `rarity_level` is changed.

## Testing & Quality

<!-- What breaks, what's flaky, what testing strategies work here -->
<!-- Format: **[YYYY-MM-DD]** Brief title — Explanation -->
**[2026-02-14]** Histogram fit is insufficient as a release gate — upload candidates need semantic checks (L1 Jaccard plus anchor precision/recall), not just target distribution match.
**[2026-02-14]** Anchor coverage must grow over time — small anchor sets are only seed protection and should be curated/expanded to keep precision-recall gates meaningful.
**[2026-02-15]** Add a fast distribution check before deep audits — `classificator rarity-distribution` gives immediate sanity checks on level skew before running heavier quality gates.
**[2026-02-15]** L1 quality needs a human loop on weakest-confidence items — use `review-low-confidence --only-levels 1` plus `l1-review-check` thresholds as an ongoing gate.
**[2026-02-20]** Recovery uploads need goal-aligned reference gating — when DB is reset or intentionally diverged, strict Jaccard/anchor thresholds against stale reference snapshots can block valid restores; confirm/refresh reference policy before running mandatory gates.

## Performance & Infrastructure

<!-- Deployment quirks, scaling lessons, CI/CD gotchas -->
<!-- Format: **[YYYY-MM-DD]** Brief title — Explanation -->
**[2026-02-14]** Local model instability requires bounded recovery tactics — retries, partial salvage, and capped batch splitting are necessary for predictable throughput.
**[2026-02-14]** Pair-level rebalance works better with stratified source mixing — mixed batches from both source levels reduce unstable transitions.

## Dependencies & External Services

<!-- Version constraints, API quirks, integration lessons -->
<!-- Format: **[YYYY-MM-DD]** Brief title — Explanation -->
**[2026-02-14]** Upload default should stay partial — only rows present in candidate CSV should update by default; `full-fallback` is an explicit exception mode.

## Process & Workflow

<!-- What makes iterations smoother, communication patterns, PR conventions -->
<!-- Format: **[YYYY-MM-DD]** Brief title — Explanation -->
**[2026-02-15]** Keep one lessons source of truth — maintain lessons only in root `LESSONS_LEARNED.md` to prevent drift between duplicated files.
**[2026-02-15]** Prefer structured per-batch logs for long rebalances — progress JSONL with picked words and counters is easier to monitor and audit than stdout-only output.

---

## Archive

<!-- Lessons that are no longer applicable. Keep for historical context. -->
<!-- Format: **[YYYY-MM-DD] Archived [YYYY-MM-DD]** Title — Reason for archival -->
