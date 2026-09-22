"""Enqueue one idempotent hourly run for each source in the approved registry."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone

from app.database import SessionLocal
from app.job_ingestion_queue import enqueue_ingestion_task
from app.source_authorization import load_authorized_sources_from_environment
from app.source_governance import SOURCE_REGISTRY, SourceApprovalError


def main() -> int:
    logging.basicConfig(level="INFO")
    logger = logging.getLogger("job_ingestion_scheduler")
    try:
        loaded = load_authorized_sources_from_environment(registry=SOURCE_REGISTRY)
    except ValueError as exc:
        logger.error("Source authorization configuration rejected: %s", type(exc).__name__)
        return 2
    if loaded:
        logger.info("Loaded %d approved job source record(s) from environment.", len(loaded))
    if not SOURCE_REGISTRY.sources():
        logger.info("No approved job sources are configured; nothing was enqueued.")
        return 0

    schedule_key = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    enqueued = 0
    blocked = 0
    db = SessionLocal()
    try:
        for source in SOURCE_REGISTRY.sources():
            try:
                _task, created = enqueue_ingestion_task(
                    db,
                    source.source_id,
                    f"{source.source_id}:{schedule_key}",
                    registry=SOURCE_REGISTRY,
                )
                enqueued += int(created)
            except SourceApprovalError as exc:
                blocked += 1
                logger.warning(
                    "Source %s remains blocked by its authorization record: %s",
                    source.source_id,
                    type(exc).__name__,
                )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not enqueue approved-source jobs.")
        return 1
    finally:
        db.close()

    logger.info("Scheduler finished: enqueued=%d blocked=%d.", enqueued, blocked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
