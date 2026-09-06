# AI Assurance Evidence Benchmark

## Ground-truth challenges

- Unsupported top-level claim
- Stale or tampered evidence
- Wrong environment or system version
- Unresolved negative evidence
- Invalidated architectural assumption
- Cyclic claim dependency
- Material change affecting a subset of claims
- Irrelevant change that should not trigger reassessment

## Publication rules

Pin case, engine and mapping versions. Publish inputs, expected results, raw outputs and reproduction commands. Regulatory breadth cannot compensate for a false supported claim. Legal interpretations are excluded from automated leaderboard claims unless independently reviewed by qualified counsel.

Primary metrics are invalidation precision/recall, unsupported-claim detection, decision reproducibility, review time and cost per defensible claim.
