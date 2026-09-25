from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Corruption → evaluate → repair → compare pipeline.

    Steps:
    1. Load baseline metrics and clean dataset.
    2. Create corrupted DataFrame.
    3. Save corrupted artifacts.
    4. Rebuild index and evaluate.
    5. Run quality checks/freshness on corrupted data.
    6. Repair from raw records (re-run cleaning).
    7. Evaluate repaired dataset.
    8. Generate comparison report.
    """
    print("=" * 60)
    print("Corruption Flow — CP4/CP5")
    print("=" * 60)

    # Step 1: Load settings and baseline artifacts
    settings = load_settings()
    run_date = now_utc()

    baseline_metrics_path = settings.paths.baseline_metrics
    if not baseline_metrics_path.exists():
        raise FileNotFoundError(
            f"Baseline metrics not found at {baseline_metrics_path}. "
            "Run Phase 1 first (script/run_phase1.py)."
        )
    baseline_metrics = read_json(baseline_metrics_path)
    print(f"[corruption_flow] Baseline hit_rate={baseline_metrics.get('retrieval_hit_rate', 0):.2%}")

    # Load clean data from snapshot
    clean_json_path = settings.paths.clean_json
    if not clean_json_path.exists():
        raise FileNotFoundError(f"Clean JSON not found: {clean_json_path}. Run Phase 1 first.")

    import pandas as pd
    df_clean = pd.read_json(clean_json_path)
    print(f"[corruption_flow] Loaded {len(df_clean)} clean rows.")

    # Step 2: Create corrupted DataFrame
    print("[corruption_flow] Applying data corruptions...")
    df_corrupted = corrupt_clean_dataframe(df_clean, settings.paths.corruption_log)

    # Step 3: Save corrupted artifacts
    write_csv(df_corrupted, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, df_corrupted.to_dict(orient="records"))
    print(f"[corruption_flow] Corrupted data saved — {len(df_corrupted)} rows.")

    # Step 4: Rebuild index and evaluate corrupted
    print("[corruption_flow] Rebuilding index on corrupted data...")
    corrupted_index = LocalEmbeddingIndex.build(
        df_corrupted, settings, embeddings_output_path=settings.paths.corrupted_embeddings_json
    )
    print("[corruption_flow] Evaluating corrupted pipeline...")
    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    corrupted_metrics = corrupted_bundle.summary
    print(
        f"[corruption_flow] Corrupted — "
        f"hit_rate={corrupted_metrics.get('retrieval_hit_rate', 0):.2%}, "
        f"f1={corrupted_metrics.get('mean_token_f1', 0):.4f}"
    )

    # Step 5: Quality checks + freshness on corrupted data
    print("[corruption_flow] Running quality checks on corrupted data...")
    corrupted_quality = run_data_quality_checks(df_corrupted, settings, "corrupted_quality_report")
    corrupted_freshness = build_freshness_report(df_corrupted, settings, settings.paths.corrupted_quality_report)

    # Step 6: Repair — re-run cleaning from raw records
    print("[corruption_flow] Repairing: re-running cleaning from raw records...")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    df_repaired = build_clean_dataframe(raw_records, run_date)
    write_csv(df_repaired, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, df_repaired.to_dict(orient="records"))
    print(f"[corruption_flow] Repaired data: {len(df_repaired)} rows.")

    # Step 7: Evaluate repaired dataset
    print("[corruption_flow] Rebuilding index on repaired data...")
    repaired_index = LocalEmbeddingIndex.build(
        df_repaired, settings, embeddings_output_path=settings.paths.repaired_embeddings_json
    )
    print("[corruption_flow] Evaluating repaired pipeline...")
    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    repaired_metrics = repaired_bundle.summary
    print(
        f"[corruption_flow] Repaired — "
        f"hit_rate={repaired_metrics.get('retrieval_hit_rate', 0):.2%}, "
        f"f1={repaired_metrics.get('mean_token_f1', 0):.4f}"
    )

    # Step 8: Quality checks on repaired + comparison report
    print("[corruption_flow] Running quality checks on repaired data...")
    repaired_quality = run_data_quality_checks(df_repaired, settings, "repaired_quality_report")
    repaired_freshness = build_freshness_report(df_repaired, settings, settings.paths.freshness_report)

    print("[corruption_flow] Generating comparison report...")
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_metrics,
        repaired_metrics=repaired_metrics,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    print("=" * 60)
    print(f"[OK] Corruption flow complete. Report -> {settings.paths.comparison_report}")
    print("=" * 60)

