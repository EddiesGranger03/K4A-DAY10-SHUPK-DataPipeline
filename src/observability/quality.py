from __future__ import annotations

from typing import Any

import great_expectations as gx
import pandas as pd

from core.config import Settings
from core.utils import write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run data quality checks using Great Expectations 1.x ephemeral context.

    Uses GX 1.x chuẩn mới (Guide.md Bước 4):
      gx.get_context(mode="ephemeral") — chạy trên RAM, không tạo file rác.

    4 Expectations bắt buộc (Rubric tiêu chí 7):
    1. ExpectTableRowCountToBeBetween          — 5 <= rows <= 5000
    2. ExpectColumnValuesToNotBeNull           — paper_id, title, text_for_embedding
    3. ExpectColumnValuesToBeUnique            — paper_id
    4. ExpectColumnValueLengthsToBeBetween     — summary >= 30 chars
    + Freshness check: age_days <= threshold on >= 75% rows
    """
    results: list[dict[str, Any]] = []
    success_overall = True

    def _record(name: str, passed: bool, observed: Any, expectation: str) -> None:
        nonlocal success_overall
        if not passed:
            success_overall = False
        results.append(
            {
                "expectation": expectation,
                "check_name": name,
                "passed": passed,
                "observed_value": observed,
            }
        )

    # ---------------------------------------------------------------
    # GX 1.x ephemeral context
    # ---------------------------------------------------------------
    try:
        context = gx.get_context(mode="ephemeral")
        data_source = context.data_sources.add_pandas(name="papers_source")
        data_asset = data_source.add_dataframe_asset(name="papers_asset")
        batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
        batch = batch_def.get_batch(batch_parameters={"dataframe": df})

        # 1. Row count 5 – 5000
        row_count = len(df)
        res1 = batch.validate(
            gx.expectations.ExpectTableRowCountToBeBetween(min_value=5, max_value=5000)
        )
        _record(
            "row_count_between_5_and_5000",
            bool(res1.success),
            row_count,
            "ExpectTableRowCountToBeBetween(min=5, max=5000)",
        )

        # 2a. paper_id not null
        res2a = batch.validate(
            gx.expectations.ExpectColumnValuesToNotBeNull(column="paper_id")
        )
        _record(
            "paper_id_not_null",
            bool(res2a.success),
            int(df["paper_id"].isna().sum()) if "paper_id" in df.columns else "N/A",
            "ExpectColumnValuesToNotBeNull(column='paper_id')",
        )

        # 2b. title not null
        res2b = batch.validate(
            gx.expectations.ExpectColumnValuesToNotBeNull(column="title")
        )
        _record(
            "title_not_null",
            bool(res2b.success),
            int((df["title"].isna() | (df["title"] == "")).sum()) if "title" in df.columns else "N/A",
            "ExpectColumnValuesToNotBeNull(column='title')",
        )

        # 2c. text_for_embedding not null
        if "text_for_embedding" in df.columns:
            res2c = batch.validate(
                gx.expectations.ExpectColumnValuesToNotBeNull(column="text_for_embedding")
            )
            _record(
                "text_for_embedding_not_null",
                bool(res2c.success),
                int(df["text_for_embedding"].isna().sum()),
                "ExpectColumnValuesToNotBeNull(column='text_for_embedding')",
            )

        # 3. paper_id unique
        res3 = batch.validate(
            gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id")
        )
        _record(
            "paper_id_unique",
            bool(res3.success),
            {"unique": int(df["paper_id"].nunique()), "total": len(df)} if "paper_id" in df.columns else "N/A",
            "ExpectColumnValuesToBeUnique(column='paper_id')",
        )

        # 4. summary length >= 30
        if "summary" in df.columns:
            res4 = batch.validate(
                gx.expectations.ExpectColumnValueLengthsToBeBetween(
                    column="summary", min_value=30
                )
            )
            _record(
                "summary_min_length_30",
                bool(res4.success),
                int((df["summary"].str.len() < 30).sum()),
                "ExpectColumnValueLengthsToBeBetween(column='summary', min=30)",
            )

    except Exception as exc:
        # GX not available or batch failed — fallback to manual checks
        print(f"[quality] GX context failed ({exc}), falling back to manual checks.")
        row_count = len(df)
        _record("row_count_between_5_and_5000", 5 <= row_count <= 5000, row_count,
                "ExpectTableRowCountToBeBetween(min=5, max=5000)")
        if "paper_id" in df.columns:
            null_c = int(df["paper_id"].isna().sum())
            _record("paper_id_not_null", null_c == 0, null_c,
                    "ExpectColumnValuesToNotBeNull(column='paper_id')")
            n_uniq = int(df["paper_id"].nunique())
            _record("paper_id_unique", n_uniq == row_count, {"unique": n_uniq, "total": row_count},
                    "ExpectColumnValuesToBeUnique(column='paper_id')")
        if "title" in df.columns:
            title_null = int((df["title"].isna() | (df["title"].str.strip() == "")).sum())
            _record("title_not_null", title_null == 0, title_null,
                    "ExpectColumnValuesToNotBeNull(column='title')")
        if "summary" in df.columns:
            short = int((df["summary"].fillna("").str.len() < 30).sum())
            _record("summary_min_length_30", short == 0, short,
                    "ExpectColumnValueLengthsToBeBetween(column='summary', min=30)")

    # Freshness SLA — Guide Bước 4: stale > 25% → is_fresh = False
    if "age_days" in df.columns:
        threshold = settings.freshness_threshold_days
        valid_age = df["age_days"].dropna()
        stale_count = int((valid_age > threshold).sum())
        stale_ratio = round(stale_count / len(valid_age), 4) if len(valid_age) > 0 else 0.0
        fresh_ok = stale_ratio <= 0.25  # flag if > 25% stale
        _record(
            "freshness_stale_ratio_lte_25pct",
            fresh_ok,
            {"stale_ratio": stale_ratio, "stale_count": stale_count, "threshold_days": threshold},
            "CustomCheck: stale_ratio <= 0.25 (Guide Bước 4)",
        )

    # Build summary report
    report = {
        "report_name": report_name,
        "passed": success_overall,
        "success": success_overall,  # alias for GX-style callers
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r["passed"]),
        "failed_checks": sum(1 for r in results if not r["passed"]),
        "results": results,
    }

    report_path = settings.paths.quality_dir / f"{report_name}.json"
    write_json(report_path, report)
    status = "PASSED" if success_overall else "FAILED"
    print(f"[quality] {report_name}: {status} ({report['passed_checks']}/{report['total_checks']} checks)")
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Compute and save a freshness report for the DataFrame.

    Fields:
    - latest_published
    - oldest_published
    - stale_rows (age_days > threshold)
    - total_rows
    - is_fresh (stale_rows == 0 or stale_ratio < 50%)
    """
    threshold = settings.freshness_threshold_days

    if "published" in df.columns:
        pub_sorted = df["published"].dropna().sort_values(ascending=False)
        latest_published = pub_sorted.iloc[0] if len(pub_sorted) > 0 else ""
        oldest_published = pub_sorted.iloc[-1] if len(pub_sorted) > 0 else ""
    else:
        latest_published = oldest_published = ""

    if "age_days" in df.columns:
        valid_age = df["age_days"].dropna()
        stale_rows = int((valid_age > threshold).sum())
    else:
        stale_rows = 0

    total_rows = len(df)
    stale_ratio = stale_rows / total_rows if total_rows > 0 else 0.0
    is_fresh = stale_ratio <= 0.25  # Guide Bước 4: > 25% stale → is_fresh = False

    payload = {
        "latest_published": str(latest_published),
        "oldest_published": str(oldest_published),
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "freshness_threshold_days": threshold,
        "is_fresh": is_fresh,
    }

    write_json(report_path, payload)
    status = "[fresh]" if is_fresh else "[STALE]"
    print(f"[freshness] {status} -- stale={stale_rows}/{total_rows} rows (threshold={threshold}d)")
    return payload

