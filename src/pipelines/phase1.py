from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion import crossref
from ingestion.cleaning import build_clean_dataframe, save_clean_artifacts
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def load_or_build_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    """Test set la 'de thi' co dinh: chi sinh lai khi REFRESH_TEST_SET=1 hoac chua co file."""
    path = settings.paths.eval_testset
    if path.exists() and not settings.refresh_test_set:
        return read_json(path)
    return build_test_set(df, path)


def _run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> None:
    """Demo agent tren 2 cau hoi; bo qua neu LLM chua cau hinh (khong lam hong pipeline)."""
    try:
        from retrieval.agent import build_agent, run_agent_question

        agent = build_agent(settings, index)
        demo = []
        for item in test_set[:2]:
            demo.append({"question": item["question"], "answer": run_agent_question(agent, item["question"])})
        write_json(settings.paths.demo_answers, demo)
        print(f"[phase1] Agent demo saved -> {settings.paths.demo_answers}")
    except Exception as exc:
        print(f"[phase1] Agent demo skipped: {type(exc).__name__}: {exc}")


def main() -> None:
    settings = load_settings()
    run_date = now_utc()
    print(f"[phase1] Run date: {run_date.isoformat(timespec='seconds')}")

    # 1-2. Ingestion (dual-mode: snapshot mac dinh, REFRESH_SOURCE=1 de goi API)
    records = crossref.fetch_source_records(settings)
    fetch_info = dict(crossref.LAST_FETCH_INFO)
    print(f"[phase1] Loaded {len(records)} raw records (mode={fetch_info.get('mode')})")

    # 3-4. Cleaning + save artifacts
    df = build_clean_dataframe(records, run_date)
    save_clean_artifacts(df, settings.paths.clean_csv, settings.paths.clean_json)
    print(f"[phase1] Clean rows: {len(df)} -> {settings.paths.clean_csv}")

    # Quality gate + freshness TRUOC khi index: du lieu xau bi chan tai day
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)
    print(f"[phase1] Quality gate passed={quality['gate_passed']} | fresh={freshness['is_fresh']}")
    if not quality["gate_passed"]:
        raise RuntimeError(
            f"Quality gate FAILED on baseline data: checks={quality['failed_checks']}, "
            f"freshness={freshness['is_fresh']}. "
            f"See {settings.paths.baseline_quality_report}"
        )

    # 5. Chroma index
    index = LocalEmbeddingIndex.build(df, settings, settings.paths.embeddings_json)
    print(f"[phase1] Chroma collection '{index.collection_name}' built with {len(index.documents)} docs")

    # 6-7. Test set + evaluation
    test_set = load_or_build_test_set(df, settings)
    print(f"[phase1] Test set: {len(test_set)} questions -> {settings.paths.eval_testset}")
    bundle = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    metrics = bundle.summary
    print(
        f"[phase1] Hit rate={metrics['retrieval_hit_rate']:.2%} | Token F1={metrics['mean_token_f1']:.3f} "
        f"| Judge acc={metrics['judge_accuracy']:.2%}"
    )

    # 9. Report
    source_summary = {
        "Source API": settings.source_api,
        "Query": settings.source_query,
        "Filter": settings.source_filter,
        "Ingestion mode": fetch_info.get("mode", "n/a"),
        "Raw response": Path(settings.paths.raw_api_response).relative_to(settings.paths.project_dir),
        "Raw records": f"{fetch_info.get('parsed_records', len(records))} parsed / {fetch_info.get('raw_items', 'n/a')} items",
        "Clean rows": len(df),
        "Run date (UTC)": run_date.isoformat(timespec="seconds"),
        "Published range": f"{df['published'].min()} → {df['published'].max()}",
        "Embedding model": settings.embedding_model,
        "Chroma collection": index.collection_name,
        "Note": fetch_info.get("note") or "-",
    }
    generate_phase1_report(
        settings.paths.baseline_report, source_summary, metrics, quality, freshness, answers=bundle.answers
    )
    print(f"[phase1] Report -> {settings.paths.baseline_report}")

    # 10. Agent demo (tuy chon)
    _run_agent_demo(settings, index, test_set)


if __name__ == "__main__":
    main()
