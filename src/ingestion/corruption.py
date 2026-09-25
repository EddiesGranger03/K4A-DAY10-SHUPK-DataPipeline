from __future__ import annotations

from datetime import UTC, datetime
import math
import random
from typing import Any

import pandas as pd

from core.utils import write_json
from ingestion.cleaning import refresh_derived_columns

SEED = 42
DROP_LATEST_RATIO = 0.20        # bo 20% bai moi nhat
FIELD_CORRUPTION_RATIO = 0.15   # moi loi blank/noise/truncate ~15% so dong
STALE_RATIO = 0.30              # > 25% de vuot nguong freshness
STALE_SHIFT_DAYS = 365
TRUNCATE_TITLE_CHARS = 7        # < 8 ky tu
NOISE_TOKENS = ["@#$%", "~~||~~", "<<>>##", "%%$$@@", "^^**^^", "#@!~$"]


def _inject_noise(text: str, rng: random.Random) -> str:
    words = str(text).split()
    if not words:
        return rng.choice(NOISE_TOKENS)
    noisy: list[str] = [rng.choice(NOISE_TOKENS)]
    for position, word in enumerate(words, start=1):
        noisy.append(word)
        if position % 3 == 0:
            noisy.append(rng.choice(NOISE_TOKENS))
    return " ".join(noisy)


def _log_entry(step: int, kind: str, description: str, df: pd.DataFrame, indexes: list[int], **params: Any) -> dict[str, Any]:
    return {
        "step": step,
        "corruption": kind,
        "description": description,
        "affected_rows": len(indexes),
        "paper_ids": [str(df.at[i, "paper_id"]) for i in indexes],
        "params": params,
    }


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Controlled corruption: 6 loi du lieu thuc te, tat dinh (seed co dinh).

    Kich ban mo phong "mot dot ingestion gan nhat bi hong": cac ban ghi moi nhat
    bi mat, dot ke tiep den noi voi field rong/nhieu/cat cut, mot phan ngay bi lui,
    va job retry nhan ban mot so dong -> tong so dong van y nguyen (silent failure).
    """
    rng = random.Random(SEED)
    data = df.copy().reset_index(drop=True)
    for column in ("authors", "categories"):
        data[column] = data[column].apply(lambda items: list(items) if isinstance(items, list) else [])
    data["published"] = pd.to_datetime(data["published"], errors="coerce").dt.strftime("%Y-%m-%d")
    data = data.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)

    input_rows = len(data)
    log: list[dict[str, Any]] = []

    # 1. Drop latest records
    n_drop = max(1, math.ceil(input_rows * DROP_LATEST_RATIO)) if input_rows > 1 else 0
    dropped = list(range(n_drop))
    log.append(_log_entry(1, "drop_latest_records", f"Dropped the {n_drop} most recent papers (lost fresh data).", data, dropped, ratio=DROP_LATEST_RATIO))
    data = data.drop(index=dropped).reset_index(drop=True)

    # 2-4. Dot ingestion ke tiep: blank / noise / truncate xoay vong tren cac dong moi nhat con lai
    n_each = max(1, round(input_rows * FIELD_CORRUPTION_RATIO))
    targets = list(range(min(len(data), n_each * 3)))
    blank_idx = targets[0::3]
    noise_idx = targets[1::3]
    trunc_idx = targets[2::3]

    for i in blank_idx:
        data.at[i, "summary"] = ""
    log.append(_log_entry(2, "blank_summary", "Summary blanked to an empty string (empty scrape).", data, blank_idx))

    for i in noise_idx:
        data.at[i, "summary"] = _inject_noise(data.at[i, "summary"], rng)
    log.append(_log_entry(3, "inject_text_noise", "Junk symbol tokens injected into summary (and text_for_embedding).", data, noise_idx, tokens=NOISE_TOKENS))

    original_titles = {i: data.at[i, "title"] for i in trunc_idx}
    for i in trunc_idx:
        data.at[i, "title"] = str(data.at[i, "title"])[:TRUNCATE_TITLE_CHARS]
    entry = _log_entry(4, "truncate_title", f"Titles truncated to {TRUNCATE_TITLE_CHARS} chars.", data, trunc_idx, max_chars=TRUNCATE_TITLE_CHARS)
    entry["original_titles"] = list(original_titles.values())
    log.append(entry)

    # 5. Stale date: lui ngay xuat ban 365 ngay tren > 25% so dong
    n_stale = min(len(data), math.ceil(input_rows * STALE_RATIO))
    stale_idx = sorted(rng.sample(range(len(data)), n_stale))
    shifted = pd.to_datetime(data.loc[stale_idx, "published"]) - pd.Timedelta(days=STALE_SHIFT_DAYS)
    data.loc[stale_idx, "published"] = shifted.dt.strftime("%Y-%m-%d").to_numpy()
    if "age_days" in data:
        data.loc[stale_idx, "age_days"] = data.loc[stale_idx, "age_days"].astype(int) + STALE_SHIFT_DAYS
    log.append(_log_entry(5, "stale_date", f"Published date shifted back {STALE_SHIFT_DAYS} days (age_days updated).", data, stale_idx, shift_days=STALE_SHIFT_DAYS))

    # 6. Duplicate rows: so dong nhan ban = so dong bi drop -> row count khong doi
    n_dup = min(len(data), n_drop) if n_drop else 1
    dup_idx = sorted(rng.sample(range(len(data)), n_dup))
    log.append(_log_entry(6, "duplicate_rows", "Rows re-inserted by a retried load job (duplicate paper_id).", data, dup_idx))
    data = pd.concat([data, data.loc[dup_idx]], ignore_index=True)

    # 7. Rebuild derived columns + text_for_embedding
    data = refresh_derived_columns(data)
    data = data[[column for column in df.columns if column in data.columns]]

    write_json(
        output_log_path,
        {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "seed": SEED,
            "input_rows": input_rows,
            "output_rows": len(data),
            "unique_paper_ids_after": int(data["paper_id"].nunique()),
            "corruptions": log,
        },
    )
    return data
