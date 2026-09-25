from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace, write_csv, write_json
from ingestion.crossref import PaperRecord, clean_markup, normalize_doi

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "abs_url",
    "pdf_url",
    "comment",
    "text_for_embedding",
]


def compose_text_for_embedding(
    title: str, authors_joined: str, published: str, categories_joined: str, summary: str
) -> str:
    """Format chuan cua 'mau banh mi' dua vao embedding model."""
    return (
        f"Title: {title}\n"
        f"Authors: {authors_joined}\n"
        f"Published: {published}\n"
        f"Categories: {categories_joined}\n"
        f"Summary: {summary}"
    )


def refresh_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Tinh lai cac cot helper tu cac cot goc (dung chung cho cleaning va corruption)."""
    df = df.copy()
    df["authors_joined"] = df["authors"].apply(lambda items: compact_join(items or []))
    df["categories_joined"] = df["categories"].apply(lambda items: compact_join(items or []))
    df["summary_chars"] = df["summary"].fillna("").astype(str).str.len().astype(int)
    df["text_for_embedding"] = [
        compose_text_for_embedding(
            row.title, row.authors_joined, row.published, row.categories_joined, row.summary
        )
        for row in df.itertuples(index=False)
    ]
    return df


def _as_utc(value: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize(UTC) if stamp.tzinfo is None else stamp.tz_convert(UTC)


def _normalize_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    result: list[str] = []
    for value in values:
        value = normalize_whitespace(str(value or ""))
        if value and value not in result:
            result.append(value)
    return result


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed."""
    rows = [asdict(record) if isinstance(record, PaperRecord) else dict(record) for record in records]
    if not rows:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    df = pd.DataFrame(rows)

    # 1. Normalize text fields
    df["paper_id"] = df["paper_id"].map(normalize_doi)
    df["title"] = df["title"].map(clean_markup)
    df["summary"] = df["summary"].map(clean_markup)
    df["authors"] = df["authors"].map(_normalize_list)
    df["categories"] = df["categories"].map(_normalize_list)
    df["primary_category"] = [
        clean_markup(primary) or (categories[0] if categories else "Uncategorized")
        for primary, categories in zip(df["primary_category"], df["categories"], strict=True)
    ]
    for column in ("abs_url", "pdf_url", "comment"):
        df[column] = df[column].fillna("").astype(str).map(normalize_whitespace)
    df["pdf_url"] = df["pdf_url"].where(df["pdf_url"] != "", df["abs_url"])

    # 2. Parse dates (ISO 8601) -> bo record khong parse duoc ngay xuat ban
    published_ts = pd.to_datetime(df["published"], utc=True, errors="coerce")
    updated_ts = pd.to_datetime(df["updated"], utc=True, errors="coerce").fillna(published_ts)
    df = df.assign(_published_ts=published_ts, _updated_ts=updated_ts)

    # 5a. Filter row xau: thieu khoa chinh, tieu de hoac ngay
    df = df[(df["paper_id"] != "") & (df["title"] != "") & df["_published_ts"].notna()].copy()

    # 3. age_days = (run_date - published).days
    run_ts = _as_utc(run_date)
    df["age_days"] = (run_ts - df["_published_ts"]).dt.days.astype(int)
    df["published"] = df["_published_ts"].dt.strftime("%Y-%m-%d")
    df["updated"] = df["_updated_ts"].dt.strftime("%Y-%m-%d")

    # 5b. Deduplicate theo paper_id, giu ban cap nhat moi nhat
    df = df.sort_values(["paper_id", "_updated_ts"], ascending=[True, False])
    df = df.drop_duplicates(subset="paper_id", keep="first")

    # 4. Helper columns + text_for_embedding
    df = refresh_derived_columns(df)

    # 6. Sort: moi nhat truoc, on dinh theo paper_id
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]


def save_clean_artifacts(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    """Ghi dataframe ra JSON (giu list) va CSV (list -> chuoi '; ')."""
    records = json.loads(df.to_json(orient="records", force_ascii=False))
    write_json(Path(json_path), records)
    csv_df = df.copy()
    for column in ("authors", "categories"):
        csv_df[column] = csv_df[column].apply(lambda items: "; ".join(items or []))
    write_csv(csv_df, Path(csv_path))


def dataframe_from_records_json(payload: list[dict[str, Any]]) -> pd.DataFrame:
    """Doc lai clean JSON thanh dataframe (giu dung kieu du lieu)."""
    df = pd.DataFrame(payload)
    for column in ("authors", "categories"):
        if column in df:
            df[column] = df[column].apply(lambda items: list(items) if isinstance(items, list) else [])
    if "published" in df:
        df["published"] = pd.to_datetime(df["published"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df
