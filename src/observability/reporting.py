from __future__ import annotations

from typing import Any

from core.utils import write_text


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a Markdown report for the baseline phase.

    Sections:
    1. Source summary (record counts, API info).
    2. Retrieval/evaluation metrics (hit rate, F1, judge accuracy).
    3. Data quality gate results.
    4. Freshness report.
    """
    lines: list[str] = []

    lines += [
        "# Phase 1 — Baseline Pipeline Report",
        "",
        f"*Generated automatically by the data pipeline.*",
        "",
    ]

    # --- 1. Source Summary ---
    lines += [
        "## 1. Source Summary",
        "",
        f"| Field | Value |",
        f"|---|---|",
    ]
    for k, v in source_summary.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # --- 2. Evaluation Metrics ---
    lines += [
        "## 2. Evaluation Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Samples | {metrics.get('samples', 'N/A')} |",
        f"| Retrieval Hit Rate | {metrics.get('retrieval_hit_rate', 0):.2%} |",
        f"| Mean Token F1 | {metrics.get('mean_token_f1', 0):.4f} |",
        f"| Judge Accuracy | {metrics.get('judge_accuracy', 0):.2%} |",
        f"| Mean Judge Score | {metrics.get('mean_judge_score', 0):.2f} / 5 |",
        "",
    ]

    ragas = metrics.get("ragas", {})
    if ragas and "skipped" not in ragas and "error" not in ragas:
        lines += ["### Ragas Metrics", "", "| Metric | Value |", "|---|---|"]
        for k, v in ragas.items():
            lines.append(f"| {k} | {v:.4f} if isinstance(v, float) else v |")
        lines.append("")

    # --- 3. Data Quality ---
    lines += [
        "## 3. Data Quality Gate",
        "",
        f"**Overall passed:** {'✅ Yes' if quality.get('passed') else '❌ No'}",
        f"**Checks:** {quality.get('passed_checks', 0)}/{quality.get('total_checks', 0)} passed",
        "",
        "| Check | Passed | Observed |",
        "|---|---|---|",
    ]
    for result in quality.get("results", []):
        status = "✅" if result.get("passed") else "❌"
        lines.append(f"| {result.get('check_name', '')} | {status} | {result.get('observed_value', '')} |")
    lines.append("")

    # --- 4. Freshness ---
    lines += [
        "## 4. Freshness Report",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Latest Published | {freshness.get('latest_published', 'N/A')} |",
        f"| Oldest Published | {freshness.get('oldest_published', 'N/A')} |",
        f"| Stale Rows | {freshness.get('stale_rows', 0)} / {freshness.get('total_rows', 0)} |",
        f"| Stale Ratio | {freshness.get('stale_ratio', 0):.2%} |",
        f"| Freshness Threshold | {freshness.get('freshness_threshold_days', 'N/A')} days |",
        f"| Is Fresh | {'✅ Yes' if freshness.get('is_fresh') else '⚠️ No'} |",
        "",
    ]

    write_text(report_path, "\n".join(lines))
    print(f"[reporting] Phase 1 report written -> {report_path}")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write a Markdown report comparing baseline / corrupted / repaired states."""

    def _fmt_pct(v) -> str:
        try:
            return f"{float(v):.2%}"
        except (TypeError, ValueError):
            return str(v)

    def _fmt_f(v, n=4) -> str:
        try:
            return f"{float(v):.{n}f}"
        except (TypeError, ValueError):
            return str(v)

    lines: list[str] = []
    lines += [
        "# Corruption & Repair — 3-State Comparison Report",
        "",
        "*Automated comparison: Baseline → Corrupted → Repaired*",
        "",
        "## 1. Retrieval & Evaluation Metrics",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Δ (Rep−Base) |",
        "|---|---|---|---|---|",
    ]

    metric_keys = [
        ("samples", "Samples", str, str, str),
        ("retrieval_hit_rate", "Hit Rate", _fmt_pct, _fmt_pct, _fmt_pct),
        ("mean_token_f1", "Mean Token F1", _fmt_f, _fmt_f, _fmt_f),
        ("judge_accuracy", "Judge Accuracy", _fmt_pct, _fmt_pct, _fmt_pct),
        ("mean_judge_score", "Mean Judge Score", lambda v: _fmt_f(v, 2), lambda v: _fmt_f(v, 2), lambda v: _fmt_f(v, 2)),
    ]
    for key, label, fmt_b, fmt_c, fmt_r in metric_keys:
        bv = baseline_metrics.get(key, "N/A")
        cv = corrupted_metrics.get(key, "N/A")
        rv = repaired_metrics.get(key, "N/A")
        try:
            delta = f"{float(rv) - float(bv):+.4f}"
        except (TypeError, ValueError):
            delta = "N/A"
        lines.append(f"| {label} | {fmt_b(bv)} | {fmt_c(cv)} | {fmt_r(rv)} | {delta} |")
    lines.append("")

    # --- Quality comparison ---
    lines += [
        "## 2. Data Quality Gate",
        "",
        "| | Corrupted | Repaired |",
        "|---|---|---|",
        f"| Overall Passed | {'✅' if corrupted_quality.get('passed') else '❌'} | {'✅' if repaired_quality.get('passed') else '❌'} |",
        f"| Checks Passed | {corrupted_quality.get('passed_checks', 0)}/{corrupted_quality.get('total_checks', 0)} | {repaired_quality.get('passed_checks', 0)}/{repaired_quality.get('total_checks', 0)} |",
        "",
    ]

    # --- Freshness comparison ---
    lines += [
        "## 3. Freshness",
        "",
        "| | Corrupted | Repaired |",
        "|---|---|---|",
        f"| Is Fresh | {'✅' if corrupted_freshness.get('is_fresh') else '⚠️'} | {'✅' if repaired_freshness.get('is_fresh') else '⚠️'} |",
        f"| Stale Rows | {corrupted_freshness.get('stale_rows', 'N/A')}/{corrupted_freshness.get('total_rows', 'N/A')} | {repaired_freshness.get('stale_rows', 'N/A')}/{repaired_freshness.get('total_rows', 'N/A')} |",
        f"| Latest Published | {corrupted_freshness.get('latest_published', 'N/A')} | {repaired_freshness.get('latest_published', 'N/A')} |",
        "",
        "---",
        "*End of report.*",
    ]

    write_text(report_path, "\n".join(lines))
    print(f"[reporting] Corruption comparison report written -> {report_path}")

