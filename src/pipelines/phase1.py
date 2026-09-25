from __future__ import annotations

from datetime import UTC, datetime

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def main() -> None:
    """Baseline pipeline end-to-end orchestrator.

    Steps:
    1. Load settings.
    2. Load or fetch raw records.
    3. Clean data.
    4. Save clean CSV/JSON.
    5. Build Chroma index.
    6. Create or load evaluation set.
    7. Evaluate.
    8. Run quality checks and freshness report.
    9. Create Markdown report.
    10. Demo agent on sample questions.
    """
    print("=" * 60)
    print("Phase 1 — Baseline Pipeline")
    print("=" * 60)

    # Step 1: Load settings
    settings = load_settings()
    run_date = now_utc()

    # Step 2: Load or fetch raw records
    raw_records_path = settings.paths.raw_records_json
    if settings.refresh_source or not raw_records_path.exists():
        print("[phase1] Fetching fresh records from Crossref API...")
        records = fetch_source_records(settings)
    else:
        print(f"[phase1] Loading records from snapshot: {raw_records_path}")
        records = load_raw_records(raw_records_path)

    if not records:
        raise RuntimeError("No records loaded. Check data/raw/ or set REFRESH_SOURCE=1.")

    # Step 3: Clean data
    print(f"[phase1] Cleaning {len(records)} raw records...")
    df = build_clean_dataframe(records, run_date)

    # Step 4: Save clean CSV/JSON
    write_csv(df, settings.paths.clean_csv)
    # Save JSON without list-valued columns (they don't serialize cleanly to CSV)
    df_json = df.copy()
    df_json["authors"] = df_json["authors"].apply(lambda x: x if isinstance(x, list) else [])
    df_json["categories"] = df_json["categories"].apply(lambda x: x if isinstance(x, list) else [])
    write_json(settings.paths.clean_json, df_json.to_dict(orient="records"))
    print(f"[phase1] Clean data saved -> {settings.paths.clean_csv}")

    source_summary = {
        "api": settings.source_api,
        "query": settings.source_query,
        "raw_records": len(records),
        "clean_records": len(df),
        "run_date": run_date.strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Step 5: Build Chroma index
    print("[phase1] Building embedding index...")
    index = LocalEmbeddingIndex.build(df, settings)
    print(f"[phase1] Index built — collection: {settings.baseline_collection_name}")

    # Step 6: Create or load evaluation set
    testset_path = settings.paths.eval_testset
    if settings.refresh_test_set or not testset_path.exists():
        print("[phase1] Building evaluation test set...")
        build_test_set(df, testset_path)
    else:
        print(f"[phase1] Using existing test set: {testset_path}")

    # Step 7: Evaluate
    print("[phase1] Running evaluation...")
    eval_bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=testset_path,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    metrics = eval_bundle.summary
    print(
        f"[phase1] Evaluation done — "
        f"hit_rate={metrics.get('retrieval_hit_rate', 0):.2%}, "
        f"f1={metrics.get('mean_token_f1', 0):.4f}"
    )

    # Step 8: Quality checks & freshness
    print("[phase1] Running data quality checks...")
    quality = run_data_quality_checks(df, settings, report_name="baseline_quality_report")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)

    # Step 9: Markdown report
    print("[phase1] Generating Phase 1 report...")
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=metrics,
        quality=quality,
        freshness=freshness,
    )

    # Step 10: Demo agent on sample questions
    print("[phase1] Running sample QA demo...")
    sample_questions = [
        "What papers discuss agentic RAG systems?",
        "Who authored the paper about data observability?",
        "When was the most recent paper published?",
    ]
    demo_answers = []
    for question in sample_questions:
        result = answer_question(question, settings=settings, index=index)
        demo_answers.append(
            {
                "question": result.question,
                "answer": result.answer,
                "retrieved_titles": result.retrieved_titles,
            }
        )
        print(f"  Q: {question}")
        print(f"  A: {result.answer[:120]}")
        print()
    write_json(settings.paths.demo_answers, demo_answers)

    print("=" * 60)
    print(f"[OK] Phase 1 complete. Report -> {settings.paths.baseline_report}")
    print("=" * 60)

