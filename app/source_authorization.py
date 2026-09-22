"""Load and validate source-authorization records without activating them.

The ingestion registry is intentionally empty until a human reviews evidence
from the source owner. This module provides the repeatable parsing and review
step. It never mutates ``SOURCE_REGISTRY`` and never fetches a URL.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .source_governance import (
    JobSource,
    SourceApprovalError,
    SourceRegistry,
    SourceStatus,
    SourceUse,
    require_approved_source,
)


REQUIRED_RECORD_FIELDS = frozenset(
    {
        "source_id",
        "display_name",
        "source_owner",
        "source_owner_reference",
        "approved_domains",
        "endpoint_url",
        "allowed_fields",
        "permitted_uses",
        "status",
        "permission_basis",
        "permission_evidence",
        "terms_reference",
        "robots_review",
        "attribution",
        "rate_limit_requests_per_minute",
        "rate_limit_max_concurrency",
        "raw_content_retention_ttl_days",
        "reviewed_at",
    }
)

SOURCE_AUTHORIZATION_RECORDS_ENV = "SOURCE_AUTHORIZATION_RECORDS_JSON"


@dataclass(frozen=True, slots=True)
class SourceAuthorizationCheck:
    """Machine-readable result for an authorization-record review."""

    source_id: str | None
    schema_valid: bool
    ready_for_registration: bool
    errors: tuple[str, ...] = ()
    approval_gaps: tuple[str, ...] = ()
    approval_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_sequence(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a JSON array")
    return tuple(value)


def source_from_record(record: Mapping[str, Any]) -> JobSource:
    """Build one ``JobSource`` from a JSON-compatible record.

    Unknown keys are rejected so a typo cannot silently remove a restriction.
    This function does not add the source to any registry.
    """

    if not isinstance(record, Mapping):
        raise ValueError("authorization record must be a JSON object")
    keys = set(record)
    missing = sorted(REQUIRED_RECORD_FIELDS - keys)
    unknown = sorted(keys - REQUIRED_RECORD_FIELDS)
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
    if unknown:
        raise ValueError("unknown fields: " + ", ".join(unknown))

    reviewed_at = record["reviewed_at"]
    if not isinstance(reviewed_at, str):
        raise ValueError("reviewed_at must be an ISO date string")
    try:
        review_date = date.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise ValueError("reviewed_at must use YYYY-MM-DD") from exc

    domains = _as_sequence(record["approved_domains"], "approved_domains")
    fields = _as_sequence(record["allowed_fields"], "allowed_fields")
    uses = _as_sequence(record["permitted_uses"], "permitted_uses")
    try:
        permitted_uses = frozenset(SourceUse(use) for use in uses)
    except (TypeError, ValueError) as exc:
        raise ValueError("permitted_uses contains an unknown right") from exc

    return JobSource(
        source_id=record["source_id"],
        display_name=record["display_name"],
        source_owner=record["source_owner"],
        source_owner_reference=record["source_owner_reference"],
        approved_domains=tuple(domains),
        endpoint_url=record["endpoint_url"],
        allowed_fields=tuple(fields),
        permitted_uses=permitted_uses,
        status=SourceStatus(record["status"]),
        permission_basis=record["permission_basis"],
        permission_evidence=record["permission_evidence"],
        terms_reference=record["terms_reference"],
        robots_review=record["robots_review"],
        attribution=record["attribution"],
        rate_limit_requests_per_minute=record["rate_limit_requests_per_minute"],
        rate_limit_max_concurrency=record["rate_limit_max_concurrency"],
        raw_content_retention_ttl_days=record["raw_content_retention_ttl_days"],
        reviewed_at=review_date,
    )


def load_source_record(path: str | Path) -> JobSource:
    """Read one UTF-8 JSON record and validate it as a ``JobSource``."""

    record_path = Path(path)
    try:
        raw = record_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read authorization record: {exc}") from exc
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"authorization record is not valid JSON: {exc.msg}") from exc
    return source_from_record(record)


def check_source(source: JobSource, *, as_of: date | None = None) -> SourceAuthorizationCheck:
    """Check readiness while preserving the fail-closed approval rules."""

    review_date = date.today() if as_of is None else as_of
    gaps = source.approval_gaps()
    approval_error: str | None = None
    try:
        require_approved_source(
            source.source_id,
            registry=SourceRegistry([source]),
            required_uses=frozenset(
                {SourceUse.AUTOMATED_FETCH, SourceUse.COMMERCIAL_DISPLAY}
            ),
            as_of=review_date,
        )
    except SourceApprovalError as exc:
        approval_error = str(exc)

    return SourceAuthorizationCheck(
        source_id=source.source_id,
        schema_valid=True,
        ready_for_registration=approval_error is None,
        approval_gaps=tuple(gaps),
        approval_error=approval_error,
    )


def check_source_record(
    record: Mapping[str, Any], *, as_of: date | None = None
) -> SourceAuthorizationCheck:
    """Validate a mapping and return actionable errors instead of raising."""

    source_id = record.get("source_id") if isinstance(record, Mapping) else None
    try:
        source = source_from_record(record)
    except (TypeError, ValueError) as exc:
        return SourceAuthorizationCheck(
            source_id=source_id if isinstance(source_id, str) else None,
            schema_valid=False,
            ready_for_registration=False,
            errors=(str(exc),),
        )
    return check_source(source, as_of=as_of)


def source_to_record(source: JobSource) -> dict[str, Any]:
    """Serialize a source without credentials or private response data."""

    record = asdict(source)
    record["permitted_uses"] = sorted(use.value for use in source.permitted_uses)
    record["status"] = source.status.value
    record["reviewed_at"] = source.reviewed_at.isoformat()
    return record


def load_authorized_sources_from_json(
    raw: str,
    *,
    registry: SourceRegistry,
    as_of: date | None = None,
) -> tuple[JobSource, ...]:
    """Validate and register a complete set of approved source records atomically.

    The payload is intentionally an environment-friendly JSON object or array.
    Every record must be fully approved before any source is registered. This
    keeps a malformed or pending record from partially activating a scheduler.
    The records contain no credentials; provider secrets remain separate Render
    environment variables.
    """

    if not isinstance(raw, str):
        raise ValueError("source authorization JSON must be text")
    if not raw.strip():
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"source authorization JSON is not valid: {exc.msg}") from exc
    if isinstance(payload, Mapping):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        raise ValueError("source authorization JSON must be an object or non-empty array")

    review_date = date.today() if as_of is None else as_of
    sources: list[JobSource] = []
    source_ids: set[str] = set()
    for item in payload:
        source = source_from_record(item)
        if source.source_id in source_ids:
            raise ValueError(f"duplicate source_id in authorization JSON: {source.source_id}")
        source_ids.add(source.source_id)
        check = check_source(source, as_of=review_date)
        if not check.ready_for_registration:
            reason = check.approval_error or ", ".join(check.approval_gaps) or "incomplete approval"
            raise ValueError(f"source {source.source_id} is not ready: {reason}")
        existing = registry.get(source.source_id)
        if existing is not None and existing != source:
            raise ValueError(f"source_id already registered with different evidence: {source.source_id}")
        sources.append(source)

    for source in sources:
        if registry.get(source.source_id) is None:
            registry.register(source)
    return tuple(sources)


def load_authorized_sources_from_environment(
    *,
    registry: SourceRegistry,
    as_of: date | None = None,
) -> tuple[JobSource, ...]:
    """Load approved records from ``SOURCE_AUTHORIZATION_RECORDS_JSON``.

    An absent variable is a valid empty registry state. Invalid input raises a
    sanitized ``ValueError`` so scheduler/worker processes fail closed without
    making a network request or activating a partial source set.
    """

    return load_authorized_sources_from_json(
        os.getenv(SOURCE_AUTHORIZATION_RECORDS_ENV, ""),
        registry=registry,
        as_of=as_of,
    )
