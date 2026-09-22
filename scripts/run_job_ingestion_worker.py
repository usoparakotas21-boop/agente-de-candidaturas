"""Run the durable approved-source JSON ingestion queue."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import socket
import time
from uuid import uuid4

from app.database import SessionLocal
from app.job_ingestion_queue import process_one_task
from app.source_authorization import load_authorized_sources_from_environment
from app.source_governance import SOURCE_REGISTRY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="process at most one item and exit")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    poll_seconds = min(60.0, max(1.0, args.poll_seconds))
    worker_id = f"{socket.gethostname()}-{uuid4().hex[:12]}"
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    logger = logging.getLogger("job_ingestion_worker")
    try:
        loaded = load_authorized_sources_from_environment(registry=SOURCE_REGISTRY)
    except ValueError as exc:
        logger.error("Source authorization configuration rejected: %s", type(exc).__name__)
        return 2
    if loaded:
        logger.info("Loaded %d approved job source record(s) from environment.", len(loaded))
    logger.info("Ingestion worker started; source registry must contain approved entries.")

    try:
        while True:
            db = SessionLocal()
            try:
                result = process_one_task(db, worker_id)
            finally:
                db.close()
            if result is not None:
                logger.info(
                    "Ingestion task completed: fetched=%d upserted=%d skipped=%d",
                    result.fetched,
                    result.upserted,
                    result.skipped,
                )
            if args.once:
                break
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        logger.info("Ingestion worker stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
