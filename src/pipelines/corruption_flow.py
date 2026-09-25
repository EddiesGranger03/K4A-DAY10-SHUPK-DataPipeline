from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import (
    build_clean_dataframe,
    dataframe_from_records_json,
    save_clean_artifacts,
)
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records, parse_crossref_payload
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import build_comparison_rows, generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _read_optional(path: Path) -> dict[str, Any] | None:
    return read_json(path) if Path(path).exists() else None


def _content_hash(df: pd.DataFrame, exclude: tuple[str, ...] = ("age_days",)) -> str:
    """Hash noi dung (bo age_days vi phu thuoc ngay chay) de chung minh idempotency."""
    columns = [c for c in df.columns if c not in exclude]
    payload = df[columns].sort_values("paper_id").to_json(orient="records", force_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def repair_from_raw(settings: Settings, run_date) -> pd.DataFrame:
    """Idempotent repair: tai tao du lieu sach tu nguon raw da bao ton (khong sua tren data loi)."""
    if settings.paths.raw_api_response.exists():
        records = parse_crossref_payload(read_json(settings.paths.raw_api_response))
    else:
        records = load_raw_records(settings.paths.raw_records_json)
    return build_clean_dataframe(records, run_date)


def _print_table(rows: list[tuple[str, str, str, str]]) -> None:
    headers = ("Metric", "Baseline", "Corrupted", "Repaired")
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(4)]
    line = " | ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    print(line)
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)))


def main() -> None:
    settings = load_settings()
    run_date = now_utc()

    # 1. Baseline artifacts (phai chay phase1 truoc)
    missing = [p for p in (settings.paths.baseline_metrics, settings.paths.clean_json, settings.paths.eval_testset) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Baseline artifacts missing — run `python script/run_phase1.py` first: "
            + ", ".join(str(p) for p in missing)
        )
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_quality = _read_optional(settings.paths.baseline_quality_report)
    baseline_freshness = _read_optional(settings.paths.freshness_report)
    clean_df = dataframe_from_records_json(read_json(settings.paths.clean_json))
    print(f"[corruption] Baseline clean rows: {len(clean_df)}")

    # 2-3. Corrupt + save
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    save_clean_artifacts(corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    print(f"[corruption] Corrupted rows: {len(corrupted_df)} -> log {settings.paths.corruption_log}")

    # 5. Quality gate + freshness tren du lieu loi
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, settings.paths.quality_dir / "corrupted_freshness_report.json"
    )
    print(
        f"[corruption] Quality gate success={corrupted_quality['success']} "
        f"failed={corrupted_quality['failed_checks']} | fresh={corrupted_freshness['is_fresh']}"
    )
    if not corrupted_quality["success"] or not corrupted_freshness["is_fresh"]:
        print("[corruption] ALERT: production gate would BLOCK this batch. Indexing anyway to measure impact.")

    # 4. Index + evaluate du lieu loi (silent failure)
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, settings.paths.corrupted_embeddings_json)
    corrupted_metrics = evaluate_pipeline(
        settings, corrupted_index, settings.paths.eval_testset,
        settings.paths.corrupted_metrics, settings.paths.corrupted_answers,
    ).summary

    # 6. Idempotent repair tu raw (chay 2 lan de chung minh cho ket qua giong het)
    repaired_df = repair_from_raw(settings, run_date)
    second_pass = repair_from_raw(settings, run_date)
    save_clean_artifacts(repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, settings.paths.quality_dir / "repaired_freshness_report.json"
    )
    if not repaired_quality["gate_passed"]:
        raise RuntimeError(
            f"Repair quality gate FAILED: checks={repaired_quality['failed_checks']}, "
            f"freshness={repaired_freshness['is_fresh']}"
        )
    repair_info = {
        "Source of truth": settings.paths.raw_api_response.name if settings.paths.raw_api_response.exists() else settings.paths.raw_records_json.name,
        "Repaired rows": len(repaired_df),
        "Idempotent (2 runs identical)": _content_hash(repaired_df) == _content_hash(second_pass),
        "Matches baseline clean data": _content_hash(repaired_df) == _content_hash(clean_df),
        "Content hash": _content_hash(repaired_df),
    }
    print(f"[repair] {repair_info}")

    # 7. Index + evaluate du lieu da phuc hoi
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, settings.paths.repaired_embeddings_json)
    repaired_metrics = evaluate_pipeline(
        settings, repaired_index, settings.paths.eval_testset,
        settings.paths.repaired_metrics, settings.paths.repaired_answers,
    ).summary

    # 8. Report + bang so sanh ra console
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics, corrupted_metrics, repaired_metrics,
        corrupted_quality, repaired_quality,
        corrupted_freshness, repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
        corruption_log=_read_optional(settings.paths.corruption_log),
        repair_info=repair_info,
    )
    print()
    _print_table(
        build_comparison_rows(
            baseline_metrics, corrupted_metrics, repaired_metrics,
            baseline_quality, corrupted_quality, repaired_quality,
            baseline_freshness, corrupted_freshness, repaired_freshness,
        )
    )
    print(f"\n[report] -> {settings.paths.comparison_report}")


if __name__ == "__main__":
    main()
