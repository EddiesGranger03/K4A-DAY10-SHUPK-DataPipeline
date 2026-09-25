from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import write_json


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build an evaluation set from the cleaned DataFrame.

    Steps:
    1. Check minimum document count.
    2. Select representative papers.
    3. Generate 4 question types per paper:
       - summary: what is the paper about?
       - authors: who authored the paper?
       - date: when was the paper published?
       - categories: what categories/subjects does the paper belong to?
    4. Each row must have: id, question_type, question, ground_truth, ground_truth_doc_ids.
    5. Write JSON to output_path.
    """
    if len(df) < 3:
        raise ValueError(f"Not enough documents to build a test set (need >= 3, got {len(df)}).")

    # Select representative papers: evenly spaced across the DataFrame
    n_papers = min(6, len(df))
    step = max(1, len(df) // n_papers)
    selected_indices = list(range(0, len(df), step))[:n_papers]
    selected = df.iloc[selected_indices].reset_index(drop=True)

    test_items: list[dict[str, Any]] = []
    item_id = 0

    for _, row in selected.iterrows():
        paper_id = str(row["paper_id"])
        title = str(row["title"])
        summary = str(row.get("summary", "") or "")
        authors_joined = str(row.get("authors_joined", "") or "")
        published = str(row.get("published", "") or "")
        categories_joined = str(row.get("categories_joined", "") or "")

        # Skip papers with insufficient data
        if not title:
            continue

        # --- Summary question ---
        test_items.append(
            {
                "id": f"q{item_id:04d}",
                "question_type": "summary",
                "question": f"What is the paper '{title}' about?",
                "ground_truth": summary if summary else title,
                "ground_truth_doc_ids": [paper_id],
            }
        )
        item_id += 1

        # --- Authors question ---
        if authors_joined:
            test_items.append(
                {
                    "id": f"q{item_id:04d}",
                    "question_type": "authors",
                    "question": f"Who authored the paper '{title}'?",
                    "ground_truth": authors_joined,
                    "ground_truth_doc_ids": [paper_id],
                }
            )
            item_id += 1

        # --- Date question ---
        if published:
            test_items.append(
                {
                    "id": f"q{item_id:04d}",
                    "question_type": "date",
                    "question": f"When was the paper '{title}' published?",
                    "ground_truth": published,
                    "ground_truth_doc_ids": [paper_id],
                }
            )
            item_id += 1

        # --- Categories question ---
        if categories_joined:
            test_items.append(
                {
                    "id": f"q{item_id:04d}",
                    "question_type": "categories",
                    "question": f"What categories does the paper '{title}' belong to?",
                    "ground_truth": categories_joined,
                    "ground_truth_doc_ids": [paper_id],
                }
            )
            item_id += 1

    write_json(output_path, test_items)
    print(f"[testset] Built {len(test_items)} test items from {len(selected)} papers -> {output_path}")
    return test_items

