"""Durable, server-only health summaries for approved job sources.

The registry remains the authority for whether a source may be fetched. This
module only measures completed queue attempts; it never grants permission and
never exposes raw feed content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import JobIngestionRun


DEFAULT_WINDOW = 20
DEFAULT_MIN_SAMPLE = 5
DEFAULT_SUCCESS_THRESHOLD = 0.80


@dataclass(frozen=True, slots=True)
class SourceHealthSummary:
    source_id: str
    sample_size: int
    succeeded: int
    failed: int
    blocked: int
    skipped_records: int
    average_latency_ms: int | None
    success_rate: float | None
    paused: bool
    last_finished_at: datetime | None


def summarize_source_health(
    db: Session,
    source_id: str,
    *,
    window: int = DEFAULT_WINDOW,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
) -> SourceHealthSummary:
    """Summarize recent completed attempts without treating missing data as healthy."""
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id is required")
    if not isinstance(window, int) or window < 1:
        raise ValueError("window must be positive")
    if not isinstance(min_sample, int) or min_sample < 1:
        raise ValueError("min_sample must be positive")
    if not 0 < float(success_threshold) <= 1:
        raise ValueError("success_threshold must be between 0 and 1")

    rows = list(
        db.scalars(
            select(JobIngestionRun)
            .where(
                JobIngestionRun.source_id == source_id,
                JobIngestionRun.status != "running",
                JobIngestionRun.finished_at.is_not(None),
            )
            .order_by(JobIngestionRun.finished_at.desc(), JobIngestionRun.id.desc())
            .limit(window)
        )
    )
    sample_size = len(rows)
    succeeded = sum(row.status == "succeeded" for row in rows)
    blocked = sum(row.status == "blocked" for row in rows)
    failed = sample_size - succeeded - blocked
    success_rate = succeeded / sample_size if sample_size else None
    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    average_latency_ms = round(sum(latencies) / len(latencies)) if latencies else None
    skipped_records = sum(max(0, int(row.skipped_count or 0)) for row in rows)
    paused = sample_size >= min_sample and (success_rate or 0.0) < float(success_threshold)
    return SourceHealthSummary(
        source_id=source_id,
        sample_size=sample_size,
        succeeded=succeeded,
        failed=failed,
        blocked=blocked,
        skipped_records=skipped_records,
        average_latency_ms=average_latency_ms,
        success_rate=success_rate,
        paused=paused,
        last_finished_at=rows[0].finished_at if rows else None,
    )

