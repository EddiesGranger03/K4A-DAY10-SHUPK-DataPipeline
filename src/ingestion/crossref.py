from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

# Crossref REST API endpoint
_CROSSREF_API = "https://api.crossref.org/works"


def _strip_jats(text: str) -> str:
    """Remove JATS XML tags (e.g. <jats:p>) from abstract text."""
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_whitespace(text)


def _parse_date_parts(date_parts: list) -> str:
    """Convert Crossref date-parts [[year, month, day]] to ISO string."""
    if not date_parts or not date_parts[0]:
        return ""
    parts = date_parts[0]
    if len(parts) >= 3:
        return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
    if len(parts) == 2:
        return f"{parts[0]:04d}-{parts[1]:02d}-01"
    return f"{parts[0]:04d}-01-01"


def _build_record(item: dict) -> PaperRecord | None:
    """Build a single PaperRecord from one Crossref item dict."""
    doi = (item.get("DOI") or "").strip()
    if not doi:
        return None

    # Title — Crossref returns a list
    title_list = item.get("title") or []
    title = normalize_whitespace(title_list[0]) if title_list else ""
    if not title:
        return None

    # Abstract — strip JATS XML tags
    abstract_raw = item.get("abstract") or ""
    summary = _strip_jats(abstract_raw)

    # Authors
    authors: list[str] = []
    for author in item.get("author") or []:
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        if family:
            authors.append(f"{given} {family}".strip())
        elif author.get("name"):
            authors.append(author["name"].strip())

    # Categories / subjects
    categories: list[str] = [s for s in (item.get("subject") or []) if s]
    primary_category = categories[0] if categories else ""

    # Dates
    published_parts = (item.get("published") or {}).get("date-parts") or []
    published = _parse_date_parts(published_parts)
    # Crossref has "created" as a datetime string; use it as "updated"
    created_dt = (item.get("created") or {}).get("date-time") or ""
    updated = created_dt[:10] if created_dt else published

    # URLs
    doi_url = item.get("URL") or f"https://doi.org/{doi}"
    abs_url = doi_url
    pdf_url = ""  # Crossref does not reliably expose PDF URLs

    return PaperRecord(
        paper_id=doi,
        title=title,
        summary=summary,
        authors=authors,
        categories=categories,
        primary_category=primary_category,
        published=published,
        updated=updated,
        abs_url=abs_url,
        pdf_url=pdf_url,
        comment="",
    )


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload into list of PaperRecord.

    Steps:
    1. Iterate payload["message"]["items"].
    2. Extract DOI, title, abstract, authors, subject, dates, URLs.
    3. Normalize text and drop invalid records.
    4. Return list[PaperRecord].
    """
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items:
        record = _build_record(item)
        if record is None:
            continue
        if record.paper_id in seen_ids:
            continue
        seen_ids.add(record.paper_id)
        records.append(record)
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Call Crossref REST API, save raw response, parse into records.

    Steps:
    1. Build params from settings.
    2. Call API with retry for 429/503.
    3. Save raw response to settings.paths.raw_api_response.
    4. Parse with parse_crossref_payload.
    5. Save records to settings.paths.raw_records_json.
    """
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "mailto": "student@lab.local",
        "select": "DOI,title,abstract,author,subject,published,created,URL",
    }

    max_retries = 4
    backoff = 2.0
    response = None
    for attempt in range(max_retries):
        try:
            response = requests.get(_CROSSREF_API, params=params, timeout=30)
            if response.status_code in (429, 503):
                wait = backoff * (2 ** attempt)
                print(f"[crossref] HTTP {response.status_code} — retrying in {wait:.0f}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Crossref API request failed after {max_retries} attempts: {exc}") from exc
            time.sleep(backoff * (2 ** attempt))

    payload = response.json()

    # Save raw API response
    write_json(settings.paths.raw_api_response, payload)
    print(f"[crossref] Raw API response saved -> {settings.paths.raw_api_response}")

    records = parse_crossref_payload(payload)
    print(f"[crossref] Parsed {len(records)} valid records from API.")

    # Save records as JSON (list of dicts)
    write_json(settings.paths.raw_records_json, [asdict(r) for r in records])
    print(f"[crossref] Records saved -> {settings.paths.raw_records_json}")

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load JSON snapshot from disk and map to list[PaperRecord]."""
    raw = read_json(path)
    records: list[PaperRecord] = []
    for item in raw:
        try:
            records.append(
                PaperRecord(
                    paper_id=item["paper_id"],
                    title=item["title"],
                    summary=item.get("summary", ""),
                    authors=item.get("authors", []),
                    categories=item.get("categories", []),
                    primary_category=item.get("primary_category", ""),
                    published=item.get("published", ""),
                    updated=item.get("updated", ""),
                    abs_url=item.get("abs_url", ""),
                    pdf_url=item.get("pdf_url", ""),
                    comment=item.get("comment", ""),
                )
            )
        except (KeyError, TypeError):
            continue  # skip malformed entries
    print(f"[crossref] Loaded {len(records)} records from {path}")
    return records

