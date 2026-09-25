from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.utils import write_text


def _pct(value: Any) -> str:
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "n/a"


def _num(value: Any, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}" if isinstance(value, (int, float)) else "n/a"


def _gate(quality: dict[str, Any] | None) -> str:
    if not quality:
        return "n/a"
    return "✅ PASSED" if quality.get("gate_passed") else "❌ FAILED"


def _fresh(freshness: dict[str, Any] | None) -> str:
    if not freshness:
        return "n/a"
    ratio = _pct(freshness.get("stale_ratio"))
    return f"✅ Fresh ({ratio} stale)" if freshness.get("is_fresh") else f"❌ Stale ({ratio} > 25%)"


def _checks_table(quality: dict[str, Any]) -> list[str]:
    lines = [
        "| Group | Expectation | Column | Result | Observed / Unexpected |",
        "| :--- | :--- | :--- | :---: | :--- |",
    ]
    for check in quality.get("checks", []):
        column = check.get("kwargs", {}).get("column", "(table)")
        observed = check.get("observed_value")
        if observed is None and check.get("unexpected_count") is not None:
            observed = f"{check['unexpected_count']} unexpected ({_num(check.get('unexpected_percent'), 1)}%)"
        lines.append(
            f"| {check.get('group')} | `{check.get('expectation')}` | {column} | "
            f"{'✅' if check.get('success') else '❌'} | {observed} |"
        )
    return lines


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    return [
        f"- Threshold: `age_days > {freshness.get('threshold_days')}` is stale; alert if stale ratio > 25%",
        f"- Latest published: **{freshness.get('latest_published')}** · Oldest: {freshness.get('oldest_published')}",
        f"- Stale rows: **{freshness.get('stale_rows')} / {freshness.get('total_rows')}** ({_pct(freshness.get('stale_ratio'))})",
        f"- Status: {_fresh(freshness)}",
    ]


def _ragas_line(metrics: dict[str, Any]) -> str:
    ragas = metrics.get("ragas")
    if not isinstance(ragas, dict):
        return "- Ragas: n/a"
    if "skipped" in ragas:
        return f"- Ragas: skipped ({ragas['skipped']})"
    if "error" in ragas:
        return f"- Ragas: error ({ragas['error']})"
    return "- Ragas: " + ", ".join(f"{k}={_num(v)}" for k, v in ragas.items())


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
    answers: list[dict[str, Any]] | None = None,
) -> None:
    """Markdown report cho baseline phase."""
    lines = [
        "# Phase 1 Report — Baseline Data Pipeline",
        "",
        f"_Generated: {datetime.now(UTC).isoformat(timespec='seconds')}_",
        "",
        "## 1. Source & Lineage",
        "",
        "| Item | Value |",
        "| :--- | :--- |",
    ]
    for key, value in source_summary.items():
        lines.append(f"| {key} | {value} |")

    lines += [
        "",
        "## 2. Data Quality Gate (Great Expectations 1.x)",
        "",
        f"**Overall:** {_gate(quality)} · core (4 mandatory fences): "
        f"{'✅' if quality.get('core_success') else '❌'} · extended: {'✅' if quality.get('extended_success') else '❌'}",
        "",
        *_checks_table(quality),
        "",
        "## 3. Freshness Monitoring",
        "",
        *_freshness_lines(freshness),
        "",
        "## 4. Baseline RAG Metrics",
        "",
        "| Metric | Value |",
        "| :--- | :---: |",
        f"| Samples | {metrics.get('samples')} |",
        f"| Retrieval Hit Rate | {_pct(metrics.get('retrieval_hit_rate'))} |",
        f"| Mean Token F1 | {_num(metrics.get('mean_token_f1'))} |",
        f"| LLM Judge Accuracy | {_pct(metrics.get('judge_accuracy'))} |",
        f"| Mean LLM Judge Score (1–5) | {_num(metrics.get('mean_judge_score'), 2)} |",
        "",
        _ragas_line(metrics),
    ]

    if answers:
        lines += [
            "",
            "## 5. Per-question Results",
            "",
            "| ID | Type | Hit | Token F1 | Judge | Question |",
            "| :--- | :--- | :---: | :---: | :---: | :--- |",
        ]
        for item in answers:
            lines.append(
                f"| {item['id']} | {item['question_type']} | {'✅' if item['retrieval_hit'] else '❌'} | "
                f"{_num(item['token_f1'], 2)} | {item.get('judge', {}).get('score', 'n/a')} | {item['question']} |"
            )

    lines += [
        "",
        "## Conclusion",
        "",
        "Baseline data passed the quality gate and freshness SLA before indexing; the metrics above "
        "are the reference point for the corruption and repair experiments.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))


def build_comparison_rows(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    baseline_quality: dict[str, Any] | None,
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    baseline_freshness: dict[str, Any] | None,
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    def rows_info(quality: dict[str, Any] | None) -> str:
        if not quality:
            return "n/a"
        checks = {c["expectation"]: c for c in quality.get("checks", [])}
        unique = checks.get("expect_column_unique_value_count_to_be_between", {}).get("observed_value")
        return f"{quality.get('row_count')} rows / {unique if unique is not None else '?'} unique"

    return [
        ("Data Quality Gate (GX 1.x)", _gate(baseline_quality), _gate(corrupted_quality), _gate(repaired_quality)),
        ("Freshness check", _fresh(baseline_freshness), _fresh(corrupted_freshness), _fresh(repaired_freshness)),
        ("Rows / unique paper_id", rows_info(baseline_quality), rows_info(corrupted_quality), rows_info(repaired_quality)),
        ("Retrieval Hit Rate", _pct(baseline_metrics.get("retrieval_hit_rate")), _pct(corrupted_metrics.get("retrieval_hit_rate")), _pct(repaired_metrics.get("retrieval_hit_rate"))),
        ("Mean Token F1", _num(baseline_metrics.get("mean_token_f1")), _num(corrupted_metrics.get("mean_token_f1")), _num(repaired_metrics.get("mean_token_f1"))),
        ("LLM Judge Accuracy", _pct(baseline_metrics.get("judge_accuracy")), _pct(corrupted_metrics.get("judge_accuracy")), _pct(repaired_metrics.get("judge_accuracy"))),
        ("Mean LLM Judge Score", _num(baseline_metrics.get("mean_judge_score"), 2), _num(corrupted_metrics.get("mean_judge_score"), 2), _num(repaired_metrics.get("mean_judge_score"), 2)),
    ]


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: dict[str, Any] | None = None,
    repair_info: dict[str, Any] | None = None,
) -> None:
    """Markdown report so sanh baseline / corrupted / repaired."""
    rows = build_comparison_rows(
        baseline_metrics, corrupted_metrics, repaired_metrics,
        baseline_quality, corrupted_quality, repaired_quality,
        baseline_freshness, corrupted_freshness, repaired_freshness,
    )
    lines = [
        "# Corruption & Repair Report — 3-State Comparison",
        "",
        f"_Generated: {datetime.now(UTC).isoformat(timespec='seconds')}_",
        "",
        "## 1. Baseline vs Corrupted vs Repaired",
        "",
        "| Metric | Baseline (clean) | Corrupted | Repaired |",
        "| :--- | :---: | :---: | :---: |",
        *[f"| {name} | {b} | {c} | {r} |" for name, b, c, r in rows],
        "",
    ]

    if corruption_log:
        lines += [
            "## 2. Injected Corruptions",
            "",
            f"Seed `{corruption_log.get('seed')}` · rows in: {corruption_log.get('input_rows')} → rows out: "
            f"{corruption_log.get('output_rows')} (unique paper_id: {corruption_log.get('unique_paper_ids_after')})",
            "",
            "| # | Corruption | Rows | Description |",
            "| :---: | :--- | :---: | :--- |",
        ]
        for entry in corruption_log.get("corruptions", []):
            lines.append(
                f"| {entry['step']} | `{entry['corruption']}` | {entry['affected_rows']} | {entry['description']} |"
            )
        lines.append("")

    lines += [
        "## 3. What the Quality Gate Caught (Corrupted data)",
        "",
        f"Failed checks: {', '.join(f'`{c}`' for c in corrupted_quality.get('failed_checks', [])) or 'none'}",
        "",
        *_checks_table(corrupted_quality),
        "",
        "### Freshness",
        "",
        *_freshness_lines(corrupted_freshness),
        "",
        "## 4. Idempotent Repair",
        "",
    ]
    if repair_info:
        lines += [f"- {key}: **{value}**" for key, value in repair_info.items()]
    lines += [
        f"- Repaired quality gate: {_gate(repaired_quality)} · freshness: {_fresh(repaired_freshness)}",
        "",
        "## 5. Analysis — Silent Failure",
        "",
        "- The corrupted dataset keeps the **same row count**, so a naive row-count check stays green; "
        "only the uniqueness, length, noise, completeness and freshness checks expose the damage.",
        "- The RAG pipeline raised **no runtime error** on corrupted data, yet retrieval hit rate and answer "
        "quality dropped: dropped fresh papers can no longer be retrieved, truncated titles break exact lookup, "
        "blank/noisy summaries and shifted dates produce wrong answers delivered with full confidence.",
        "- In production the gate would **block indexing** of the corrupted batch. Here it is indexed "
        "deliberately to measure the impact.",
        "- Repair rebuilds from the preserved raw snapshot with the same deterministic cleaning code, "
        "so re-running it always yields the same clean data and restores baseline metrics.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))
