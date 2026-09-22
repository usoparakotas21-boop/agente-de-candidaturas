"""Pure adapters for approved job-feed payloads.

The ingestion gate still decides whether a source may be fetched.  These
adapters only reshape an already-authorized JSON response into the flat fields
accepted by :mod:`app.job_ingestion`; they never make network requests, follow
redirects, or enable a source in the registry.
"""

from __future__ import annotations

from typing import Any, Iterable


def _text(value: Any) -> str:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip()
    return ""


def _nested_text(value: Any, *keys: str) -> str:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _text(current)


def _lever(record: dict[str, Any]) -> dict[str, Any]:
    categories = record.get("categories") if isinstance(record.get("categories"), dict) else {}
    salary = record.get("salaryRange") if isinstance(record.get("salaryRange"), dict) else {}
    return {
        "external_id": _text(record.get("id")),
        "title": _text(record.get("text")) or _text(record.get("title")),
        "company": _text(record.get("company")),
        "location": _text(categories.get("location")),
        "description": _text(record.get("descriptionPlain")) or _text(record.get("description")),
        "apply_url": _text(record.get("applyUrl")) or _text(record.get("hostedUrl")),
        "salary_range": " - ".join(
            value for value in (_text(salary.get("min")), _text(salary.get("max"))) if value
        ),
        "work_mode": _text(categories.get("workplaceType")),
        "contract_type": _text(categories.get("commitment")),
    }


def _greenhouse(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_id": _text(record.get("id")),
        "title": _text(record.get("title")),
        "company": _text(record.get("company")),
        "location": _nested_text(record.get("location"), "name"),
        "description": _text(record.get("content")) or _text(record.get("description")),
        "apply_url": _text(record.get("absolute_url")) or _text(record.get("apply_url")),
        "salary_range": _text(record.get("salary_range")),
        "work_mode": _text(record.get("work_mode")),
        "contract_type": _text(record.get("contract_type")),
    }


def _adzuna(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten one Adzuna API result without retaining provider-only fields."""
    company = record.get("company") if isinstance(record.get("company"), dict) else {}
    location = record.get("location") if isinstance(record.get("location"), dict) else {}
    salary_values = (_text(record.get("salary_min")), _text(record.get("salary_max")))
    return {
        "external_id": _text(record.get("id")),
        "title": _text(record.get("title")),
        "company": _text(company.get("display_name")) or _text(company.get("name")),
        "location": _text(location.get("display_name")) or _text(location.get("area")),
        "description": _text(record.get("description")),
        "apply_url": _text(record.get("redirect_url")) or _text(record.get("url")),
        "salary_range": " - ".join(value for value in salary_values if value),
        "work_mode": _text(record.get("work_mode")),
        "contract_type": _text(record.get("contract_type")),
    }


def _jooble(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten one Jooble API result without following its application link."""
    return {
        "external_id": _text(record.get("id")) or _text(record.get("job_id")),
        "title": _text(record.get("title")),
        "company": _text(record.get("company")),
        "location": _text(record.get("location")),
        "description": _text(record.get("snippet")) or _text(record.get("description")),
        "apply_url": _text(record.get("link")) or _text(record.get("url")),
        "salary_range": _text(record.get("salary")),
        "work_mode": _text(record.get("work_mode")),
        "contract_type": _text(record.get("type")) or _text(record.get("contract_type")),
    }


def adapt_feed_records(source_id: str, records: Iterable[Any]) -> list[Any]:
    """Flatten known authorized feed shapes without changing unknown sources."""

    adapter = {
        "lever": _lever,
        "lever-postings": _lever,
        "greenhouse": _greenhouse,
        "greenhouse-job-board": _greenhouse,
        "adzuna": _adzuna,
        "adzuna-api": _adzuna,
        "jooble": _jooble,
        "jooble-api": _jooble,
    }.get(str(source_id).strip().casefold())
    if adapter is None:
        return list(records)
    return [adapter(record) if isinstance(record, dict) else record for record in records]
