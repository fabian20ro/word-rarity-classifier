# Lessons Learned

- Strict parser contracts outperform permissive recovery for long multi-pass rebalance chains.
- Most costly regressions came from id-domain ambiguity (`word_id` vs `local_id`) in Step5.
- Quality gates must be semantic (L1 stability + anchor checks), not only distributional.
- Resume/checkpoint artifacts are operationally critical when runs take hours.
- Small prompt wording changes can materially shift L1 composition; treat prompt files as versioned assets.
