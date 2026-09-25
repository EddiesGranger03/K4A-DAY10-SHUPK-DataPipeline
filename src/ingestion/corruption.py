from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd

from core.utils import write_json

_SEED = 42


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate multiple forms of data corruption on a clean DataFrame.

    Corruption types:
    1. Drop some latest records (simulate data loss / freshness gap).
    2. Blank summary on some rows (simulate missing data).
    3. Inject noise characters into text (simulate encoding issues).
    4. Truncate title to 20 chars on some rows (simulate truncation bug).
    5. Age the published date by 400+ days (simulate stale data).
    6. Add duplicate rows (simulate pipeline re-run without dedup).
    7. Rebuild text_for_embedding.
    8. Write corruption log to output_log_path.
    """
    rng = random.Random(_SEED)
    corrupted = df.copy()
    log: list[dict] = []

    n = len(corrupted)
    if n == 0:
        write_json(output_log_path, log)
        return corrupted

    # ------------------------------------------------------------------
    # 1. Drop 20% latest records (Guide Bước 7)
    n_drop = max(1, int(n * 0.20))
    if "published" in corrupted.columns:
        corrupted = corrupted.sort_values("published", ascending=False).reset_index(drop=True)
    drop_indices = corrupted.index[:n_drop].tolist()
    dropped_ids = corrupted.loc[drop_indices, "paper_id"].tolist()
    corrupted = corrupted.drop(index=drop_indices).reset_index(drop=True)
    log.append({"type": "drop_rows", "paper_ids": dropped_ids, "count": len(dropped_ids)})

    # ------------------------------------------------------------------
    # 2. Blank summary on ~15% of rows
    # ------------------------------------------------------------------
    blank_idx = [i for i in range(len(corrupted)) if rng.random() < 0.15]
    if blank_idx:
        corrupted.loc[blank_idx, "summary"] = ""
        log.append({"type": "blank_summary", "row_indices": blank_idx, "count": len(blank_idx)})

    # ------------------------------------------------------------------
    # 3. Inject noise into summary text on ~20% of rows
    # ------------------------------------------------------------------
    noise_chars = "!@#$%^&*"
    noise_idx = [i for i in range(len(corrupted)) if rng.random() < 0.20]
    for i in noise_idx:
        original = corrupted.at[i, "summary"]
        noise = "".join(rng.choice(noise_chars) for _ in range(8))
        corrupted.at[i, "summary"] = original + " " + noise
    if noise_idx:
        log.append({"type": "inject_noise", "row_indices": noise_idx, "count": len(noise_idx)})

    # ------------------------------------------------------------------
    # 4. Truncate title to < 8 chars on ~10% of rows (Guide Bước 7)
    trunc_idx = [i for i in range(len(corrupted)) if rng.random() < 0.10]
    for i in trunc_idx:
        corrupted.at[i, "title"] = corrupted.at[i, "title"][:7]  # max 7 chars → < 8
    if trunc_idx:
        log.append({"type": "truncate_title", "row_indices": trunc_idx, "count": len(trunc_idx)})

    # ------------------------------------------------------------------
    # 5. Age published date by 365 days on ~20% of rows (Guide Bước 7)
    stale_idx = [i for i in range(len(corrupted)) if rng.random() < 0.20]
    for i in stale_idx:
        pub_str = corrupted.at[i, "published"]
        try:
            pub_date = datetime.strptime(pub_str[:10], "%Y-%m-%d")
            corrupted.at[i, "published"] = (pub_date - timedelta(days=365)).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
    if stale_idx:
        log.append({"type": "stale_published_date", "row_indices": stale_idx, "count": len(stale_idx)})

    # ------------------------------------------------------------------
    # 6. Add duplicate rows (pick ~10% of rows, append as dupes)
    # ------------------------------------------------------------------
    n_dupes = max(1, len(corrupted) // 10)
    dup_indices = rng.sample(range(len(corrupted)), min(n_dupes, len(corrupted)))
    dupe_rows = corrupted.iloc[dup_indices].copy()
    corrupted = pd.concat([corrupted, dupe_rows], ignore_index=True)
    log.append({"type": "add_duplicates", "row_indices": dup_indices, "count": len(dup_indices)})

    # ------------------------------------------------------------------
    # 7. Rebuild text_for_embedding (5-part format, same as cleaning.py)
    corrupted["text_for_embedding"] = (
        "Title: " + corrupted["title"].fillna("") + "\n"
        + "Authors: " + corrupted["authors_joined"].fillna("") + "\n"
        + "Published: " + corrupted["published"].fillna("") + "\n"
        + "Categories: " + corrupted["categories_joined"].fillna("") + "\n"
        + "Summary: " + corrupted["summary"].fillna("")
    ).str.strip()

    # ------------------------------------------------------------------
    # 8. Write corruption log
    # ------------------------------------------------------------------
    write_json(output_log_path, log)
    print(f"[corruption] Applied {len(log)} corruption types. Output: {len(corrupted)} rows.")
    print(f"[corruption] Log saved -> {output_log_path}")

    return corrupted

