# Verified plan reuse: findings

The frozen held-out study completed **768 endpoint runs over 64 clusters**, with two repetitions of six conditions. Verified reuse reduced cost per successful resolution by **38.4%** and warm median latency by **44.9%** against fused planning.

Verified reuse resolved 122/128 endpoints versus 122/128 for fused planning. It had 0 incorrect accepted reuse hits, 0 observed harmful clusters, and 0 executed authorization violations. These are mechanical path/required-fact judgments, not semantic or human answer-quality certification.

**Empty-bank tail:** verified p95 was 8.2% higher than fused empty-bank p95. The warm median gains do not establish a miss-path tail-latency improvement.

Prefer exact-skeleton reuse for v1: it meets the engineering cost/median-latency targets with no observed harmful clusters. Semantic compatibility remains useful evidence, but this workload does not require its added complexity to meet those targets.

|Condition|Resolved|Appropriate abstentions|USD/resolution|p50 ms|p95 ms|Reuse hits|Incorrect hits|
|---|---:|---:|---:|---:|---:|---:|---:|
|exact:warm|122/128|6|0.001117|1896|4164|64|0|
|fused:empty|122/128|4|0.001750|3572|4440|0|0|
|fused:warm|122/128|6|0.001853|3490|4501|0|0|
|ordinary:warm|106/128|2|0.001028|1776|3541|94|18|
|verified:empty|122/128|4|0.001797|3591|4802|0|0|
|verified:warm|122/128|6|0.001141|1922|3977|68|0|

## Paired uncertainty and tails

Verified paired 95% cluster-bootstrap intervals: success-rate difference 0.0% to 0.0%; cost reduction 24.6% to 50.0%; median-latency reduction 41.1% to 50.5%.

The conservative 95% upper bound on harmful-cluster rate is 4.6%. This does not establish a 1% production-risk guarantee. Because instances share family wording, the exploratory eight-family zero-event bound is 31.2%; independence assumptions matter.

Verified p95 latency is 3977 ms versus 4501 ms for fused planning. The exploratory paired p95-reduction interval is -7.8% to 18.1%. Tail results remain visible regardless of the median.

## Cost, construction, and provenance

All phases used 1537 real model calls, with 0 usage-unknown calls. Reuse-study committed cost was $1.5394; the shared global ledger total was $2.0412. The study retains 96 earlier pilot endpoints, charged to budget and excluded from final comparisons.

The frozen bank contains 14 admitted plans from 16 attempted history executions. It stores slots and dependencies rather than arguments, results, or answers. Eight family contracts were approved; generated substitutions remain derived references. The frozen source/configuration archive and all journals remain available.

API construction cost was $0.0730. Estimated warm requests to amortize construction: exact 105, verified 108. Full scenarios are in analysis/test/summary.json.

Repeat-rate scenarios are estimates that scale measured warm-workload savings linearly; they assume no additional miss cost. They are not measured production traffic. Costs use actual API usage with frozen pricing assumptions, and exclude engineering/review labor.

## Observed semantic reuse errors

Incorrect accepted reuse endpoints by family: {'issues': 4, 'sources': 4, 'calculations': 8, 'comparisons': 2}. The diagnostic retained all authorization/schema/returned-binding guards. Those guards do not prove semantic intent. See runs.jsonl for exact paths and responses. The bad-result flag conservatively marks answer generation after an incorrect path; it does not prove an incorrect resource was mentioned to the user.

![quality-cost](analysis/test/quality-cost.png)

![latency-components](analysis/test/latency-components.png)

![hit-miss](analysis/test/hit-miss.png)

![reuse-errors](analysis/test/reuse-errors.png)

![break-even](analysis/test/break-even.png)

## Limits

This is a small, deliberately recurring, read-only local fixture workload with real model calls. Unresolved and appropriately abstained requests are not completed resolutions. Mechanical scoring, selected wording, provider caching, and only 64 independent clusters constrain generalization. There is no production deployment, concurrency SLO, result cache, or formal privacy claim.
