from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import compact_join, first_sentence, write_json

MIN_DOCUMENTS = 4
DEFAULT_QUESTION_COUNT = 10
# 10 cau chia cho 4 dang: summary x3, authors x3, date x2, categories x2
QUESTION_TYPES = ["summary", "authors", "date", "categories"]

# Template khop voi cac pattern trong retrieval/qa.py (_extract_answer)
# va dat title trong dau nhay don de qa.answer_question lookup chinh xac.
QUESTION_TEMPLATES = {
    "summary": "What is the summary of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}


def _joined(row: pd.Series, joined_column: str, list_column: str) -> str:
    value = row.get(joined_column)
    if isinstance(value, str) and value:
        return value
    items = row.get(list_column)
    return compact_join(items) if isinstance(items, list) else ""


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return first_sentence(str(row["summary"]))
    if question_type == "authors":
        return _joined(row, "authors_joined", "authors")
    if question_type == "date":
        return str(row["published"])
    return _joined(row, "categories_joined", "categories")


def build_test_set(
    df: pd.DataFrame, output_path, num_questions: int = DEFAULT_QUESTION_COUNT
) -> list[dict[str, Any]]:
    """Tao bo evaluation set (ground truth co dinh) tu cleaned dataframe.

    Chon cac paper moi nhat (dung loai du lieu nguoi dung hay hoi nhat va
    nhay cam nhat voi su co mat du lieu tuoi), moi paper 1 cau hoi, xoay vong
    4 dang cau hoi.
    """
    if df is None or len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} clean documents to build a test set.")

    candidates = df.copy()
    candidates = candidates[
        candidates["title"].astype(str).str.len().ge(10)
        & ~candidates["title"].astype(str).str.contains("'", regex=False)
        & candidates["summary"].astype(str).str.len().ge(30)
    ]
    candidates = candidates.drop_duplicates(subset="paper_id")
    candidates = candidates.sort_values(["published", "paper_id"], ascending=[False, True])

    samples: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(candidates.head(num_questions).iterrows()):
        question_type = QUESTION_TYPES[position % len(QUESTION_TYPES)]
        ground_truth = _ground_truth(row, question_type)
        if not ground_truth:
            continue
        samples.append(
            {
                "id": f"eval_{len(samples) + 1:03d}",
                "question_type": question_type,
                "question": QUESTION_TEMPLATES[question_type].format(title=row["title"]),
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )

    expected_counts = {question_type: num_questions // len(QUESTION_TYPES) for question_type in QUESTION_TYPES}
    for question_type in QUESTION_TYPES[: num_questions % len(QUESTION_TYPES)]:
        expected_counts[question_type] += 1
    actual_counts = {question_type: 0 for question_type in QUESTION_TYPES}
    for sample in samples:
        actual_counts[sample["question_type"]] += 1
    if len(samples) != num_questions or actual_counts != expected_counts:
        raise ValueError(
            f"Could not build the required evaluation set: expected {num_questions} questions "
            f"with counts {expected_counts}, got {len(samples)} with counts {actual_counts}."
        )

    write_json(output_path, samples)
    return samples
