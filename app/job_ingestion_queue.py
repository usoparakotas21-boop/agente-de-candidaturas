"""Durable, database-backed queue for approved public JSON job feeds.

PostgreSQL is the production queue backend; SQLite remains supported for local
single-worker development and tests. Every enqueue and processing path checks
source governance. The queue itself is never exposed through a client API.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .job_ingestion import IngestionResult, ingest_authorized_json_feed
from .job_ingestion_health import summarize_source_health
from .models import JobIngestionRun, JobIngestionTask, utc_now
from .source_governance import (
    SOURCE_REGISTRY,
    SourceApprovalError,
    SourceRegistry,
    SourceUse,
    require_approved_source,
)

MAX_ATTEMPTS = 5
LEASE_SECONDS = 90
RETRY_BACKOFF_SECONDS = (60, 300, 900, 3600)
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,179}$")


@dataclass(frozen=True, slots=True)
class ClaimedTask:
    task_id: int
    source_id: str
    attempts: int
    lease_token: str


def enqueue_ingestion_task(
    db: Session,
    source_id: str,
    idempotency_key: str,
    *,
    registry: SourceRegistry = SOURCE_REGISTRY,
) -> tuple[JobIngestionTask, bool]:
    """Insert one authorized task exactly once for the caller's run key."""
    if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_RE.fullmatch(idempotency_key):
        raise ValueError("Use an idempotency key of 1–180 safe ASCII characters.")
    require_approved_source(
        source_id,
        registry=registry,
        required_uses=(
            SourceUse.AUTOMATED_FETCH,
            SourceUse.COMMERCIAL_DISPLAY,
            SourceUse.DESCRIPTION_CACHING,
        ),
    )
    dialect = db.bind.dialect.name if db.bind is not None else ""
    insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert is None:
        raise RuntimeError("The ingestion queue requires PostgreSQL or SQLite.")

    statement = (
        insert(JobIngestionTask)
        .values(
            source_id=source_id,
            idempotency_key=idempotency_key,
            status="pending",
            attempts=0,
            available_at=utc_now(),
        )
        .on_conflict_do_nothing(index_elements=[JobIngestionTask.idempotency_key])
        .returning(JobIngestionTask.id)
    )
    inserted_id = db.execute(statement).scalar_one_or_none()
    task = (
        db.get(JobIngestionTask, inserted_id)
        if inserted_id is not None
        else db.scalar(
            select(JobIngestionTask).where(
                JobIngestionTask.idempotency_key == idempotency_key
            )
        )
    )
    if task is None:
        raise RuntimeError("Could not resolve the queued ingestion task.")
    if task.source_id != source_id:
        raise ValueError("Idempotency key is already assigned to another source.")
    return task, inserted_id is not None


def claim_next_task(
    db: Session,
    worker_id: str,
    *,
    lease_seconds: int = LEASE_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
) -> ClaimedTask | None:
    """Atomically claim the oldest ready item; recover expired worker leases."""
    now = utc_now()
    expired_max = and_(
        JobIngestionTask.status == "running",
        JobIngestionTask.locked_until <= now,
        JobIngestionTask.attempts >= max_attempts,
    )
    db.execute(
        update(JobIngestionTask)
        .where(expired_max)
        .values(
            status="failed",
            last_error_code="worker_lease_expired",
            locked_by=None,
            locked_until=None,
            lease_token=None,
            finished_at=now,
            updated_at=now,
        )
    )

    ready_status = and_(
        JobIngestionTask.status.in_(("pending", "retry")),
        JobIngestionTask.available_at <= now,
    )
    recoverable_lease = and_(
        JobIngestionTask.status == "running",
        JobIngestionTask.locked_until <= now,
    )
    eligible = and_(or_(ready_status, recoverable_lease), JobIngestionTask.attempts < max_attempts)
    candidate_query = (
        select(JobIngestionTask.id)
        .where(eligible)
        .order_by(JobIngestionTask.available_at, JobIngestionTask.id)
        .limit(1)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        candidate_query = candidate_query.with_for_update(skip_locked=True)

    token = secrets.token_hex(24)
    result = db.execute(
        update(JobIngestionTask)
        .where(JobIngestionTask.id == candidate_query.scalar_subquery(), eligible)
        .values(
            status="running",
            attempts=JobIngestionTask.attempts + 1,
            locked_by=worker_id[:80],
            locked_until=now + timedelta(seconds=max(10, int(lease_seconds))),
            lease_token=token,
            last_error_code=None,
            updated_at=now,
        )
        .returning(
            JobIngestionTask.id,
            JobIngestionTask.source_id,
            JobIngestionTask.attempts,
        )
    )
    row = result.first()
    db.commit()
    if row is None:
        return None
    return ClaimedTask(
        task_id=int(row.id),
        source_id=str(row.source_id),
        attempts=int(row.attempts),
        lease_token=token,
    )


def _record_failure(
    db: Session,
    claim: ClaimedTask,
    error: Exception,
    *,
    max_attempts: int,
) -> bool:
    now = utc_now()
    permanent = isinstance(error, SourceApprovalError)
    failed = permanent or claim.attempts >= max_attempts
    delay = RETRY_BACKOFF_SECONDS[min(claim.attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
    values = {
        "status": "failed" if failed else "retry",
        "available_at": now if failed else now + timedelta(seconds=delay),
        "last_error_code": type(error).__name__[:100],
        "locked_by": None,
        "locked_until": None,
        "lease_token": None,
        "finished_at": now if failed else None,
        "updated_at": now,
    }
    result = db.execute(
        update(JobIngestionTask)
        .where(
            JobIngestionTask.id == claim.task_id,
            JobIngestionTask.status == "running",
            JobIngestionTask.lease_token == claim.lease_token,
        )
        .values(**values)
    )
    db.commit()
    return result.rowcount == 1


def process_one_task(
    db: Session,
    worker_id: str,
    *,
    registry: SourceRegistry = SOURCE_REGISTRY,
    ingester: Callable[..., IngestionResult] = ingest_authorized_json_feed,
    max_attempts: int = MAX_ATTEMPTS,
) -> IngestionResult | None:
    """Process one task; return ``None`` when the queue is idle or lease is lost."""
    claim = claim_next_task(db, worker_id, max_attempts=max_attempts)
    if claim is None:
        return None
    started_at = utc_now()
    run = JobIngestionRun(
        task_id=claim.task_id,
        source_id=claim.source_id,
        status="running",
        started_at=started_at,
    )
    db.add(run)
    db.commit()
    run_id = run.id
    try:
        health = summarize_source_health(db, claim.source_id)
        if health.paused:
            finished_at = utc_now()
            update_result = db.execute(
                update(JobIngestionTask)
                .where(
                    JobIngestionTask.id == claim.task_id,
                    JobIngestionTask.status == "running",
                    JobIngestionTask.lease_token == claim.lease_token,
                )
                .values(
                    status="failed",
                    locked_by=None,
                    locked_until=None,
                    lease_token=None,
                    last_error_code="source_health_paused",
                    finished_at=finished_at,
                    updated_at=finished_at,
                )
            )
            if update_result.rowcount != 1:
                db.rollback()
                run = db.get(JobIngestionRun, run_id)
                if run is not None:
                    run.status = "retry"
                    run.error_code = "lease_lost"
                    run.finished_at = finished_at
                    run.latency_ms = max(0, round((finished_at - started_at).total_seconds() * 1000))
                    db.commit()
                return None
            run = db.get(JobIngestionRun, run_id)
            if run is not None:
                run.status = "blocked"
                run.error_code = "source_health_paused"
                run.finished_at = finished_at
                run.latency_ms = max(0, round((finished_at - started_at).total_seconds() * 1000))
            db.commit()
            logging.getLogger(__name__).warning(
                "Ingestion task %s blocked by source health for %s.",
                claim.task_id,
                claim.source_id,
            )
            return None
        result = ingester(db, claim.source_id, registry=registry)
        finished_at = utc_now()
        update_result = db.execute(
            update(JobIngestionTask)
            .where(
                JobIngestionTask.id == claim.task_id,
                JobIngestionTask.status == "running",
                JobIngestionTask.lease_token == claim.lease_token,
            )
            .values(
                status="succeeded",
                locked_by=None,
                locked_until=None,
                lease_token=None,
                last_error_code=None,
                finished_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        if update_result.rowcount != 1:
            db.rollback()
            run = db.get(JobIngestionRun, run_id)
            if run is not None:
                run.status = "retry"
                run.error_code = "lease_lost"
                run.finished_at = finished_at
                run.latency_ms = max(0, round((finished_at - started_at).total_seconds() * 1000))
                db.commit()
            return None
        run = db.get(JobIngestionRun, run_id)
        if run is not None:
            run.status = "succeeded"
            run.finished_at = finished_at
            run.latency_ms = max(0, round((finished_at - started_at).total_seconds() * 1000))
            run.fetched_count = max(0, int(result.fetched))
            run.upserted_count = max(0, int(result.upserted))
            run.skipped_count = max(0, int(result.skipped))
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        persisted = _record_failure(db, claim, exc, max_attempts=max_attempts)
        if persisted:
            status = db.scalar(
                select(JobIngestionTask.status).where(JobIngestionTask.id == claim.task_id)
            )
            logging.getLogger(__name__).warning(
                "Ingestion task %s entered %s after %s.",
                claim.task_id,
                status or "unknown",
                type(exc).__name__,
            )
        run = db.get(JobIngestionRun, run_id)
        if run is not None:
            finished_at = utc_now()
            task_status = db.scalar(
                select(JobIngestionTask.status).where(JobIngestionTask.id == claim.task_id)
            )
            run.status = "blocked" if isinstance(exc, SourceApprovalError) else (
                task_status if task_status in {"retry", "failed"} else "failed"
            )
            run.error_code = type(exc).__name__[:100]
            run.finished_at = finished_at
            run.latency_ms = max(0, round((finished_at - started_at).total_seconds() * 1000))
            db.commit()
        return None
