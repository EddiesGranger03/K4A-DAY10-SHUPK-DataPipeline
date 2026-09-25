from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 20

_TAG_RE = re.compile(r"<[^>]+>")
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.IGNORECASE)

# Thong tin lan fetch gan nhat (live / snapshot) de pipeline dua vao bao cao.
LAST_FETCH_INFO: dict[str, Any] = {}


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


# ---------------------------------------------------------------------------
# Helpers chuan hoa
# ---------------------------------------------------------------------------

def normalize_doi(value: str | None) -> str:
    """DOI khong phan biet hoa thuong -> bo prefix URL va lowercase."""
    if not value:
        return ""
    return _DOI_PREFIX_RE.sub("", str(value).strip()).strip().lower()


def clean_markup(value: str | None) -> str:
    """Bo the JATS/HTML (<jats:p>, <i>, ...), unescape entity va gom khoang trang."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    return normalize_whitespace(html.unescape(text))


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        value = next((item for item in value if item), "")
    return clean_markup(value)


def _date_from_parts(block: Any) -> str:
    """Crossref date: {"date-parts": [[2026, 5, 20]]} hoac {"date-time": "..."} -> YYYY-MM-DD."""
    if not isinstance(block, dict):
        return ""
    parts = block.get("date-parts") or []
    if parts and parts[0] and parts[0][0]:
        year, month, day = (list(parts[0]) + [1, 1])[:3]
        try:
            return datetime(int(year), int(month or 1), int(day or 1)).date().isoformat()
        except (TypeError, ValueError):
            pass
    date_time = block.get("date-time")
    if date_time:
        try:
            return datetime.fromisoformat(str(date_time).replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return ""
    return ""


def _first_date(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        parsed = _date_from_parts(item.get(key))
        if parsed:
            return parsed
    return ""


def _parse_authors(raw_authors: Any) -> list[str]:
    authors: list[str] = []
    for author in raw_authors or []:
        if not isinstance(author, dict):
            continue
        name = author.get("name") or " ".join(
            part for part in (author.get("given"), author.get("family")) if part
        )
        name = normalize_whitespace(str(name))
        if name and name not in authors:
            authors.append(name)
    return authors


def _parse_categories(raw_subjects: Any) -> list[str]:
    categories: list[str] = []
    for subject in raw_subjects or []:
        subject = normalize_whitespace(str(subject))
        if subject and subject not in categories:
            categories.append(subject)
    return categories


def _pdf_url(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("link") or []:
        if isinstance(link, dict) and "pdf" in str(link.get("content-type", "")).lower() and link.get("URL"):
            return str(link["URL"])
    return fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord, bo record thieu DOI/title/ngay."""
    items = (payload or {}).get("message", {}).get("items", []) or []
    records: list[PaperRecord] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        paper_id = normalize_doi(item.get("DOI"))
        title = _first_text(item.get("title"))
        published = _first_date(
            item, ("published", "published-online", "published-print", "issued", "created")
        )
        if not paper_id or not title or not published or paper_id in seen:
            continue
        seen.add(paper_id)

        categories = _parse_categories(item.get("subject"))
        abs_url = str(item.get("URL") or f"https://doi.org/{paper_id}")
        updated = _first_date(item, ("updated", "deposited", "indexed")) or published

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=clean_markup(item.get("abstract")),
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "Uncategorized",
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=_pdf_url(item, abs_url),
                comment=f"Crossref record {paper_id}",
            )
        )
    return records


def _request_crossref(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (student lab)"}
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(f"Crossref returned {response.status_code}", response=response)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("message", {}).get("items"):
                raise ValueError("Crossref response has no items.")
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("Retry-After")
            wait = float(retry_after) if retry_after and str(retry_after).isdigit() else 2 ** attempt
            print(f"[crossref] Attempt {attempt} failed ({exc}); retrying in {wait:.0f}s...")
            time.sleep(min(wait, 30))
    raise RuntimeError(f"Crossref API unavailable after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Dual-mode ingestion.

    - Mac dinh (offline/dev): doc snapshot `data/raw/crossref_response.json` neu co.
    - REFRESH_SOURCE=1 (hoac chua co snapshot): goi Crossref API co retry.
      Neu API loi (429/503/mat mang) -> tu dong fallback ve snapshot.
    Raw response chi bi ghi de khi goi API thanh cong (raw preservation).
    """
    raw_path = settings.paths.raw_api_response
    payload: dict[str, Any] | None = None
    mode = "snapshot"
    note = ""

    if settings.refresh_source or not raw_path.exists():
        try:
            payload = _request_crossref(settings)
            write_json(raw_path, payload)
            mode = "live"
        except Exception as exc:  # network/429/parse errors -> fallback
            note = f"Live API failed, fallback to snapshot: {exc}"
            print(f"[crossref] {note}")

    if payload is None:
        if not raw_path.exists():
            raise FileNotFoundError(
                f"No Crossref snapshot at {raw_path} and the live API is unavailable."
            )
        payload = read_json(raw_path)

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])

    LAST_FETCH_INFO.clear()
    LAST_FETCH_INFO.update(
        {
            "mode": mode,
            "raw_response_path": str(raw_path),
            "raw_records_path": str(settings.paths.raw_records_json),
            "raw_items": len(payload.get("message", {}).get("items", []) or []),
            "parsed_records": len(records),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "note": note,
        }
    )
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot (list dict) va map thanh PaperRecord."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Raw records file not found: {path}")
    payload = read_json(path)
    if isinstance(payload, dict) and "message" in payload:
        # Cho phep truyen thang raw Crossref response.
        return parse_crossref_payload(payload)

    field_names = [field.name for field in fields(PaperRecord)]
    records: list[PaperRecord] = []
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        values: dict[str, Any] = {}
        for name in field_names:
            value = row.get(name)
            if name in {"authors", "categories"}:
                value = [str(item) for item in value] if isinstance(value, list) else []
            else:
                value = "" if value is None else str(value)
            values[name] = value
        if values["paper_id"] and values["title"]:
            records.append(PaperRecord(**values))
    return records
