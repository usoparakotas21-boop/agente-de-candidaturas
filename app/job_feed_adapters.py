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


def _workable(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten the public Workable jobs shape without retaining provider-only fields."""
    location = record.get("location") if isinstance(record.get("location"), dict) else {}
    company = record.get("company") if isinstance(record.get("company"), dict) else {}
    salary = record.get("salary") if isinstance(record.get("salary"), dict) else {}
    location_text = " / ".join(
        value
        for value in (
            _text(location.get("city")),
            _text(location.get("region")),
            _text(location.get("country")),
        )
        if value
    ) or " / ".join(
        value
        for value in (_text(record.get("city")), _text(record.get("state")), _text(record.get("country")))
        if value
    )
    salary_values = (
        _text(salary.get("salary_from")),
        _text(salary.get("salary_to")),
        _text(record.get("salary_from")),
        _text(record.get("salary_to")),
    )
    return {
        "external_id": _text(record.get("shortcode")) or _text(record.get("id")) or _text(record.get("code")),
        "title": _text(record.get("title")) or _text(record.get("full_title")),
        "company": _text(company.get("name")) or _text(record.get("company")),
        "location": location_text,
        "description": _text(record.get("full_description")) or _text(record.get("description")),
        "apply_url": _text(record.get("application_url")) or _text(record.get("url")) or _text(record.get("shortlink")),
        "salary_range": " - ".join(value for value in salary_values if value)[:200],
        "work_mode": _text(record.get("workplace_type")) or _text(location.get("workplace_type")),
        "contract_type": _text(record.get("employment_type")),
    }


def _smartrecruiters(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten SmartRecruiters postings/feed records without following their URLs."""
    company = record.get("company") if isinstance(record.get("company"), dict) else {}
    location = record.get("location") if isinstance(record.get("location"), dict) else {}
    employment = record.get("typeOfEmployment") if isinstance(record.get("typeOfEmployment"), dict) else {}
    job_ad = record.get("jobAd") if isinstance(record.get("jobAd"), dict) else {}
    sections = job_ad.get("sections") if isinstance(job_ad.get("sections"), dict) else {}
    description_parts = []
    for section_name in ("jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(section_name)
        if isinstance(section, dict):
            value = _text(section.get("text"))
        else:
            value = _text(job_ad.get(section_name))
        if value:
            description_parts.append(value)
    location_text = " / ".join(
        value
        for value in (_text(location.get("city")), _text(location.get("region")), _text(location.get("country")))
        if value
    )
    compensation = record.get("compensation") if isinstance(record.get("compensation"), dict) else {}
    return {
        "external_id": _text(record.get("id")) or _text(record.get("uuid")),
        "title": _text(record.get("name")) or _text(record.get("title")),
        "company": _text(company.get("name")),
        "location": location_text,
        "description": "\n\n".join(description_parts),
        "apply_url": _text(record.get("applyUrl")) or _text(record.get("postingUrl")) or _text(record.get("jobAdUrl")),
        "salary_range": _text(compensation.get("salary")) or _text(compensation.get("label")),
        "work_mode": "remote" if location.get("remote") is True else _text(location.get("workplaceType")),
        "contract_type": _text(employment.get("label")) or _text(employment.get("name")),
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
        "workable": _workable,
        "workable-api": _workable,
        "smartrecruiters": _smartrecruiters,
        "smartrecruiters-feed": _smartrecruiters,
    }.get(str(source_id).strip().casefold())
    if adapter is None:
        return list(records)
    return [adapter(record) if isinstance(record, dict) else record for record in records]
