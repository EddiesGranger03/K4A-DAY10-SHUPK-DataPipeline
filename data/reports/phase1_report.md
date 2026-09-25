# Phase 1 — Baseline Pipeline Report

*Generated automatically by the data pipeline.*

## 1. Source Summary

| Field | Value |
|---|---|
| api | Crossref REST API |
| query | agentic retrieval augmented generation large language model |
| raw_records | 24 |
| clean_records | 24 |
| run_date | 2026-09-25 09:42 UTC |

## 2. Evaluation Metrics

| Metric | Value |
|---|---|
| Samples | 24 |
| Retrieval Hit Rate | 100.00% |
| Mean Token F1 | 0.9089 |
| Judge Accuracy | 100.00% |
| Mean Judge Score | 4.50 / 5 |

## 3. Data Quality Gate

**Overall passed:** ✅ Yes
**Checks:** 7/7 passed

| Check | Passed | Observed |
|---|---|---|
| row_count_between_5_and_5000 | ✅ | 24 |
| paper_id_not_null | ✅ | 0 |
| title_not_null | ✅ | 0 |
| text_for_embedding_not_null | ✅ | 0 |
| paper_id_unique | ✅ | {'unique': 24, 'total': 24} |
| summary_min_length_30 | ✅ | 0 |
| freshness_stale_ratio_lte_25pct | ✅ | {'stale_ratio': 0.0417, 'stale_count': 1, 'threshold_days': 180} |

## 4. Freshness Report

| Field | Value |
|---|---|
| Latest Published | 2026-07-22 |
| Oldest Published | 2026-03-28 |
| Stale Rows | 1 / 24 |
| Stale Ratio | 4.17% |
| Freshness Threshold | 180 days |
| Is Fresh | ✅ Yes |
