# Iteration Log

> Append-only journal of AI agent work sessions on this project.
> **Add an entry at the end of every iteration.**
> When patterns emerge (same issue 2+ times), promote to `LESSONS_LEARNED.md`.

## Format

Each entry should follow this structure:

---

### [YYYY-MM-DD] Brief Description of Work Done

**Context:** What was the goal / what triggered this work
**What happened:** Key actions taken, decisions made
**Outcome:** Result — success, partial, or failure
**Insight:** (optional) What would you tell the next agent about this?
**Promoted to Lessons Learned:** Yes/No

---

### [2026-02-15] Uploaded final rebalance output to Supabase

**Context:** Rebalance run finished with target distribution (`L4=25k`, rest of previous L4 moved to L5).
**What happened:** Ran `step4-upload` in partial mode for `rb_l4split25k_20260215_134927.csv` and validated DB distribution with direct SQL counts.
**Outcome:** Success. DB now reflects `1:1234, 2:6610, 3:12517, 4:25000, 5:32337`.
**Insight:** N/A
**Promoted to Lessons Learned:** No

---

### [2026-02-15] Mirrored Step5 batch progress into main run log

**Context:** Requested batch progress visibility in the main log stream used for tailing.
**What happened:** Updated Step5 to append each batch progress payload to both `rebalance/progress/<run>.progress.jsonl` and `rebalance/runs/<run>.jsonl` (`event=batch_progress`), added tests, and ran full unit suite.
**Outcome:** Success. New/resumed Step5 processes now expose per-batch progress directly in the primary run log.
**Insight:** Logging progress in the same stream operators already tail reduces observability friction during long retries.
**Promoted to Lessons Learned:** No

---

### [2026-02-15] Added Step5 structured progress logs with picked words

**Context:** Needed Step5 logs to show explicit progress and exactly which words were picked per batch.
**What happened:** Added `rebalance/progress/<run>.progress.jsonl` output with per-batch counters and picked word ids/words, kept checkpoint compatibility for resume, added tests, and updated runbook docs.
**Outcome:** Success. New Step5 runs (or resumed runs after restart) produce progress logs suitable for live tailing and audit.
**Insight:** Checkpoint-compatible logging allows richer observability without sacrificing resumability.
**Promoted to Lessons Learned:** Yes

---

### [2026-02-15] Started level-4 to level-5 rebalance run in tmux

**Context:** Requested rebalance to keep about 25k words on level 4 and move the remainder of current level-4 words to level 5.
**What happened:** Started Step5 run `rb_l4split25k_20260215_134927` in detached tmux with transition `4:4` and `--lower-ratio 0.45589657` from input `initial_20260215_034523.csv`.
**Outcome:** In progress. Process is running in tmux and writing Step5 run logs under `build/rarity/rebalance/runs/`.
**Insight:** For this objective, transition `4:4` is the correct split mode; it controls the kept count in level 4 while moving the rest to level 5.
**Promoted to Lessons Learned:** No

---

### [2026-02-15] Uploaded new run and added low-confidence review app with L1 gate

**Context:** Requested production upload of the latest run and a way to continuously validate Level 1 quality with human review.
**What happened:** Uploaded `build/rarity/runs/initial_20260215_034523.csv` via `step4-upload` (partial), implemented `review-low-confidence`/`review` interactive labeling app, implemented `l1-review-check` threshold gate, and integrated docs/tests.
**Outcome:** Success. New rarity levels are uploaded, and an operator workflow now exists to review lowest-confidence words and enforce L1 precision thresholds.
**Insight:** Combining anchor checks with recurring low-confidence human review gives stronger L1 protection than either alone.
**Promoted to Lessons Learned:** Yes

---

### [2026-02-15] Compared latest Step2 run with current DB rarity levels

**Context:** Needed Jaccard and distribution comparison between latest generated run and currently stored DB levels.
**What happened:** Exported current DB levels to `build/rarity/reference/current_db_levels.csv`, ran `rarity-distribution` on candidate/reference, then ran `quality-audit` with `--reference-csv`.
**Outcome:** Success. Produced L1 Jaccard and side-by-side distribution snapshots for direct comparison.
**Insight:** N/A
**Promoted to Lessons Learned:** No

---

### [2026-02-15] Added rarity-distribution CLI utility and docs integration

**Context:** Needed a quick way to inspect rarity level distribution directly from generated CSV outputs.
**What happened:** Implemented `classificator rarity-distribution` (alias `dist`), added parser/tests, updated README/RUNBOOK/AGENTS docs, and executed it on the latest Step2 output.
**Outcome:** Success. Distribution can now be checked with a single command and is integrated into operational docs.
**Insight:** Fast distribution visibility helps catch obvious skew earlier in the pipeline.
**Promoted to Lessons Learned:** Yes

---

### [2026-02-15] Consolidated lessons into single root file

**Context:** Requested to merge duplicate lessons files into the root project lessons file.
**What happened:** Merged remaining unique wording from `docs/LESSONS_LEARNED.md` into root `LESSONS_LEARNED.md`, updated README reference, removed the duplicate docs file, and ran unit tests plus a `quality-audit` smoke command.
**Outcome:** Success. Lessons are now maintained in one authoritative location at project root, and verification commands passed.
**Insight:** Keeping a single lessons source prevents divergence in future agent sessions.
**Promoted to Lessons Learned:** Yes

---

### [2026-02-14] Synced docs and memory with external system contract

**Context:** Imported the updated external classifier description from the `propozitii-nostime` reference document.
**What happened:** Updated boundary/contract docs (`README`, onboarding, handover, pipeline design), recorded validated operational lessons in both lessons files, ran unit tests, and executed a `quality-audit` smoke command.
**Outcome:** Success. Repository docs now reflect current ownership boundary, strict Step5 rules, mandatory semantic quality gates, and partial-upload default; verification commands passed.
**Insight:** Cross-repo boundary wording should be kept explicit to prevent runtime/code ownership confusion.
**Promoted to Lessons Learned:** Yes

---

<!-- New entries go above this line, most recent first -->
