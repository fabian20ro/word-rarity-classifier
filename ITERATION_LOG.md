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
