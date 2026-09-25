from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into a DataFrame ready for embedding.

    Steps:
    1. Normalize title, summary, authors, categories.
    2. Parse published/updated date.
    3. Compute age_days.
    4. Create helper columns:
       - authors_joined
       - categories_joined
       - summary_chars
       - text_for_embedding
    5. Drop duplicates and filter bad rows.
    6. Sort DataFrame and return.
    """
    rows = []
    for rec in records:
        title = normalize_whitespace(rec.title)
        summary = normalize_whitespace(rec.summary)

        # Normalize authors list
        authors_clean = [normalize_whitespace(a) for a in rec.authors if a.strip()]
        categories_clean = [normalize_whitespace(c) for c in rec.categories if c.strip()]

        # Parse published date
        published_str = rec.published or ""
        try:
            pub_date = datetime.strptime(published_str[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            pub_date = None

        # Compute age_days relative to run_date
        run_naive = run_date.replace(tzinfo=None) if run_date.tzinfo else run_date
        age_days = (run_naive - pub_date).days if pub_date else None

        rows.append(
            {
                "paper_id": rec.paper_id,
                "title": title,
                "summary": summary,
                "authors": authors_clean,
                "categories": categories_clean,
                "primary_category": normalize_whitespace(rec.primary_category),
                "published": published_str[:10] if published_str else "",
                "updated": (rec.updated or "")[:10],
                "abs_url": rec.abs_url or "",
                "pdf_url": rec.pdf_url or "",
                "comment": rec.comment or "",
                "age_days": age_days,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # --- Helper columns ---
    df["authors_joined"] = df["authors"].apply(lambda lst: compact_join(lst, ", "))
    df["categories_joined"] = df["categories"].apply(lambda lst: compact_join(lst, ", "))
    df["summary_chars"] = df["summary"].str.len()

    # text_for_embedding: 5-part format per Guide.md Bước 3
    # Title: <tiêu đề>
    # Authors: <tác giả>
    # Published: <ngày>
    # Categories: <lĩnh vực>
    # Summary: <tóm tắt>
    df["text_for_embedding"] = (
        "Title: " + df["title"] + "\n"
        + "Authors: " + df["authors_joined"] + "\n"
        + "Published: " + df["published"] + "\n"
        + "Categories: " + df["categories_joined"] + "\n"
        + "Summary: " + df["summary"]
    ).str.strip()

    # --- Drop duplicates ---
    df = df.drop_duplicates(subset=["paper_id"])
    df = df.drop_duplicates(subset=["title"])

    # --- Filter bad rows ---
    # Must have title
    df = df[df["title"].str.len() > 0]
    # Must have some content for embedding
    df = df[df["text_for_embedding"].str.len() > 10]

    # --- Sort by published date descending (newest first) ---
    df = df.sort_values("published", ascending=False).reset_index(drop=True)

    print(f"[cleaning] Clean DataFrame: {len(df)} rows after dedup/filter.")
    return df

