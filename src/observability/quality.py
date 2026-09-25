from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")

import great_expectations as gx  # noqa: E402

from core.config import Settings  # noqa: E402
from core.utils import read_json, safe_slug, write_json  # noqa: E402

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MIN_TITLE_CHARS = 10
MAX_STALE_RATIO = 0.25
# Chuoi >= 3 ky tu dac biet lien tiep: dau hieu nhieu/rac trong van ban.
NOISE_REGEX = r"[@#$%^*~|<>]{3,}"


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _expected_source_rows(settings: Settings) -> int | None:
    """So paper_id duy nhat trong raw snapshot -> doi soat nguon vs dich (completeness)."""
    path = settings.paths.raw_records_json
    try:
        payload = read_json(path)
        ids = {str(row.get("paper_id", "")).strip().lower() for row in payload if isinstance(row, dict)}
        ids.discard("")
        return len(ids) or None
    except Exception:
        return None


def _build_expectations(expected_rows: int | None) -> list[tuple[str, Any]]:
    """(nhom, expectation). 'core' = 4 hang rao bat buoc theo de bai; 'extended' = bo sung."""
    E = gx.expectations
    expectations: list[tuple[str, Any]] = [
        ("core", E.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS)),
        ("core", E.ExpectColumnValuesToNotBeNull(column="paper_id")),
        ("core", E.ExpectColumnValuesToNotBeNull(column="title")),
        ("core", E.ExpectColumnValuesToNotBeNull(column="text_for_embedding")),
        ("core", E.ExpectColumnValuesToBeUnique(column="paper_id")),
        ("core", E.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS)),
        # --- Extended: bat nhung loi ma 4 hang rao bat buoc bo lot ---
        ("extended", E.ExpectColumnValueLengthsToBeBetween(column="title", min_value=MIN_TITLE_CHARS)),
        ("extended", E.ExpectColumnValuesToNotMatchRegex(column="summary", regex=NOISE_REGEX)),
        ("extended", E.ExpectColumnValuesToNotMatchRegex(column="text_for_embedding", regex=NOISE_REGEX)),
    ]
    if expected_rows:
        expectations.append(
            (
                "extended",
                E.ExpectColumnUniqueValueCountToBeBetween(column="paper_id", min_value=expected_rows),
            )
        )
    return expectations


def _compute_freshness(df: pd.DataFrame, threshold_days: int) -> dict[str, Any]:
    total = int(len(df))
    published = pd.to_datetime(df.get("published"), errors="coerce", utc=True)
    if "age_days" in df:
        ages = pd.to_numeric(df["age_days"], errors="coerce")
    else:
        ages = (pd.Timestamp(datetime.now(UTC)) - published).dt.days
    stale_rows = int((ages > threshold_days).sum())
    stale_ratio = (stale_rows / total) if total else 1.0
    return {
        "threshold_days": threshold_days,
        "max_stale_ratio": MAX_STALE_RATIO,
        "latest_published": published.max().strftime("%Y-%m-%d") if published.notna().any() else None,
        "oldest_published": published.min().strftime("%Y-%m-%d") if published.notna().any() else None,
        "min_age_days": int(ages.min()) if ages.notna().any() else None,
        "max_age_days": int(ages.max()) if ages.notna().any() else None,
        "stale_rows": stale_rows,
        "total_rows": total,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": bool(total > 0 and stale_ratio <= MAX_STALE_RATIO),
    }


def _report_path(settings: Settings, report_name: str) -> Path:
    mapping = {
        "baseline": settings.paths.baseline_quality_report,
        "corrupted": settings.paths.corrupted_quality_report,
    }
    return mapping.get(report_name, settings.paths.quality_dir / f"{safe_slug(report_name)}_quality_report.json")


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Data Quality Gate bang Great Expectations 1.x + freshness check."""
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    expected_rows = _expected_source_rows(settings)
    planned = _build_expectations(expected_rows)
    suite = context.suites.add(gx.ExpectationSuite(name=f"papers_quality_{safe_slug(report_name)}"))
    for _, expectation in planned:
        suite.add_expectation(expectation)

    validation = batch.validate(suite)

    group_by_id = {str(expectation.id): group for group, expectation in planned}
    checks: list[dict[str, Any]] = []
    for result in validation.results:
        config = result.expectation_config
        kwargs = {k: v for k, v in (config.kwargs or {}).items() if k != "batch_id"}
        detail = result.result or {}
        checks.append(
            {
                "group": group_by_id.get(str(config.id), "extended"),
                "expectation": config.type,
                "kwargs": kwargs,
                "success": bool(result.success),
                "observed_value": detail.get("observed_value"),
                "unexpected_count": detail.get("unexpected_count"),
                "unexpected_percent": detail.get("unexpected_percent"),
                "partial_unexpected_list": (detail.get("partial_unexpected_list") or [])[:5],
            }
        )
    order = {"core": 0, "extended": 1}
    checks.sort(key=lambda check: order.get(check["group"], 2))

    core_success = all(check["success"] for check in checks if check["group"] == "core")
    extended_success = all(check["success"] for check in checks if check["group"] == "extended")
    freshness = _compute_freshness(df, settings.freshness_threshold_days)

    report = _jsonable(
        {
            "report_name": report_name,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "gx_version": gx.__version__,
            "row_count": int(len(df)),
            "expected_source_rows": expected_rows,
            "success": bool(validation.success),
            "core_success": core_success,
            "extended_success": extended_success,
            "failed_checks": [
                f"{c['expectation']}({c['kwargs'].get('column', 'table')})" for c in checks if not c["success"]
            ],
            "checks": checks,
            "freshness": freshness,
            "gate_passed": bool(validation.success and freshness["is_fresh"]),
        }
    )
    write_json(_report_path(settings, report_name), report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness report va ghi JSON."""
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **_compute_freshness(df, settings.freshness_threshold_days),
    }
    write_json(Path(report_path), _jsonable(payload))
    return payload
