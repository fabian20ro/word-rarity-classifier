# AGENTS.md

> Non-discoverable operating constraints for AI agents.
> If the model can find it in the codebase, it does not belong here.
> For corrections and patterns, see `LESSONS_LEARNED.md`.

## Constraints

1. **Step5 selection contract is strict.**
   LM output must be exact-count local ids (`1..N`, no duplicates, no `0`).
   Never reintroduce silent auto-fill of missing selections.

2. **Upload gating is mandatory.**
   Pre-upload candidate must be checked with Jaccard and anchor precision/recall.
   Do not upload based only on histogram fit.

3. **CSV-first operation.**
   Keep all step artifacts explicit and resumable.
   Avoid hidden in-memory-only workflows.

4. **Upload mode default is `partial`.**
   Use `full-fallback` only with explicit intent.

## Legacy & Deprecated

<!-- Parts of the codebase that would actively mislead the model.
     Add entries here only for non-obvious traps. Remove when the code is cleaned up. -->

## Learning System

This project uses a persistent learning system. Follow this workflow every session:

1. **Start of task:** Read `LESSONS_LEARNED.md` — it contains validated corrections and patterns
2. **During work:** Note any surprises or non-obvious discoveries
3. **End of iteration:** Append to `ITERATION_LOG.md` with what happened
4. **If insight is reusable and validated:** Also add to `LESSONS_LEARNED.md`
5. **If same issue appears 2+ times in log:** Promote to `LESSONS_LEARNED.md`
6. **If something surprised you:** Flag it to the developer

| File | Purpose | When to Write |
|------|---------|---------------|
| `LESSONS_LEARNED.md` | Curated, validated wisdom and corrections | When insight is reusable |
| `ITERATION_LOG.md` | Raw session journal (append-only, never delete) | Every iteration (always) |

Rules: Never delete from ITERATION_LOG. Obsolete lessons → Archive section in LESSONS_LEARNED (not deleted). Date-stamp everything YYYY-MM-DD. When in doubt: log it.

### Periodic Maintenance

- Review `LESSONS_LEARNED.md` quarterly; archive stale entries
- After major pipeline changes, verify sub-agent files still apply
- AGENTS.md should shrink over time, not grow — prefer fixing the codebase over adding entries here

## Sub-Agents

Specialized agents in `.claude/agents/`. Invoke proactively — don't wait to be asked.

| Agent | File | Invoke When |
|-------|------|-------------|
| Architect | `.claude/agents/architect.md` | System design, scalability, refactoring, ADRs |
| Planner | `.claude/agents/planner.md` | Complex multi-step features — plan before coding |
| Agent Creator | `.claude/agents/agent-creator.md` | Need a new specialized agent for a recurring task domain |
