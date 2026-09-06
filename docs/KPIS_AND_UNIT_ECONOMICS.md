# KPI and unit-economics contract

Proposed targets are pilot gates, not measured customer outcomes.

| KPI | Formula | Evidence | Proposed gate |
|---|---|---|---:|
| Provenance coverage | evidence with producer and source / evidence | Graph | 100% critical |
| Integrity validation | matching digests / local evidence | Hash verification | 100% |
| Evidence freshness | unexpired applicable evidence / required evidence | Graph clock | ≥95% |
| Environment equivalence | correct-environment evidence / required evidence | Deployment metadata | 100% critical |
| Reproduction success | successful independent reproductions / attempts | CI records | ≥95% |
| Context completeness | claims with bounded context / claims | Claim review | 100% |
| Ownership coverage | claims with accountable owner / claims | Directory acknowledgement | 100% |
| Invalidation recall | correctly invalidated ground-truth claims / affected claims | Change fixtures | ≥95% |
| Invalidation precision | correctly invalidated claims / all invalidations | Change fixtures | ≥90% |
| Change-to-invalidation | material change timestamp → decision update | Event history | P90 <15 minutes |

## Economics

| Measure | Formula | Guardrail |
|---|---|---|
| Cost per assurance case | total assurance cost / completed cases | Comparable case class |
| Cost per defensible claim | total cost / claims surviving independent review | Exclude unsupported claims |
| Evidence reuse | reused applicable evidence / evidence | Require context equivalence |
| Marginal assurance cost | added cost for one system/version/jurisdiction | Report scope |
| Change-impact savings | avoided reassessment hours × loaded cost | Baseline time study |
| Expected loss reduction | probability × impact × demonstrated effectiveness | P10/P50/P90 |
| Revenue-weighted days | Σ value × days removed / term days | Timing, not created revenue |
| Capacity-enabled pipeline | extra reviews × qualification × average value | Never booked revenue |
| Net assurance value | risk + savings + attributable revenue − cost | Exclude capacity pipeline |

Every revenue assertion requires a deal or service identifier, customer requirement, baseline and actual date, attribution class, finance-approved factor, approver and source provenance.
