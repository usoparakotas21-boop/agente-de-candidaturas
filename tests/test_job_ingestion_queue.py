import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.job_ingestion import IngestionResult
from app.job_ingestion_queue import (
    claim_next_task,
    enqueue_ingestion_task,
    process_one_task,
)
from app.models import JobIngestionTask, utc_now
from app.source_governance import (
    JobSource,
    SourceApprovalError,
    SourceRegistry,
    SourceStatus,
    SourceUse,
)


def make_source(source_id="pilot-board", domain="jobs.example.com"):
    return JobSource(
        source_id=source_id,
        display_name="Pilot board",
        source_owner="Example Hiring Ltd.",
        source_owner_reference=f"https://{domain}/legal/company",
        approved_domains=(domain,),
        endpoint_url=f"https://{domain}/api/v1/jobs",
        allowed_fields=("external_id", "title", "company", "location", "description", "apply_url"),
        permitted_uses=frozenset({
            SourceUse.AUTOMATED_FETCH,
            SourceUse.COMMERCIAL_DISPLAY,
            SourceUse.DESCRIPTION_CACHING,
        }),
        status=SourceStatus.APPROVED,
        permission_basis="Written permission from source owner",
        permission_evidence="https://docs.example.com/permission/123",
        terms_reference=f"https://{domain}/terms",
        robots_review="Reviewed 2026-09-20; authorized JSON feed",
        attribution="Show source name and original listing link",
        rate_limit_requests_per_minute=12,
        rate_limit_max_concurrency=1,
        raw_content_retention_ttl_days=30,
        reviewed_at=date.today(),
    )


class JobIngestionQueueTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        JobIngestionTask.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.source = make_source()
        self.registry = SourceRegistry([self.source])

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_enqueue_is_idempotent_and_requires_approved_source(self):
        task, created = enqueue_ingestion_task(
            self.db, self.source.source_id, "pilot:2026-09-21T12", registry=self.registry
        )
        duplicate, duplicate_created = enqueue_ingestion_task(
            self.db, self.source.source_id, "pilot:2026-09-21T12", registry=self.registry
        )
        self.db.commit()
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(task.id, duplicate.id)
        self.assertEqual(self.db.scalars(select(JobIngestionTask)).all().__len__(), 1)

        with self.assertRaises(SourceApprovalError):
            enqueue_ingestion_task(
                self.db, "linkedin", "linkedin:2026-09-21T12", registry=self.registry
            )

    def test_idempotency_key_cannot_be_reused_for_another_source(self):
        second = make_source("second-board", "jobs.second.example.com")
        registry = SourceRegistry([self.source, second])
        enqueue_ingestion_task(self.db, self.source.source_id, "shared-key", registry=registry)
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "another source"):
            enqueue_ingestion_task(self.db, second.source_id, "shared-key", registry=registry)

    def test_claim_is_exclusive_and_expired_lease_is_recovered(self):
        enqueue_ingestion_task(self.db, self.source.source_id, "pilot:one", registry=self.registry)
        self.db.commit()
        first = claim_next_task(self.db, "worker-a", lease_seconds=10)
        self.assertIsNotNone(first)
        self.assertEqual(first.attempts, 1)
        self.assertIsNone(claim_next_task(self.db, "worker-b", lease_seconds=10))

        self.db.execute(
            update(JobIngestionTask)
            .where(JobIngestionTask.id == first.task_id)
            .values(locked_until=utc_now() - timedelta(seconds=1))
        )
        self.db.commit()
        recovered = claim_next_task(self.db, "worker-b", lease_seconds=10)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.task_id, first.task_id)
        self.assertEqual(recovered.attempts, 2)
        self.assertNotEqual(recovered.lease_token, first.lease_token)

    def test_success_commits_task_and_ingestion_result(self):
        enqueue_ingestion_task(self.db, self.source.source_id, "pilot:success", registry=self.registry)
        self.db.commit()
        expected = IngestionResult(fetched=3, upserted=2, skipped=1)

        result = process_one_task(
            self.db,
            "worker-test",
            registry=self.registry,
            ingester=lambda _db, _source_id, **_kwargs: expected,
        )
        task = self.db.scalar(select(JobIngestionTask))
        self.assertEqual(result, expected)
        self.assertEqual(task.status, "succeeded")
        self.assertIsNotNone(task.finished_at)
        self.assertIsNone(task.lease_token)

    def test_transient_failure_enters_backoff_retry_state(self):
        enqueue_ingestion_task(self.db, self.source.source_id, "pilot:retry", registry=self.registry)
        self.db.commit()
        before = utc_now()
        process_one_task(
            self.db,
            "worker-test",
            registry=self.registry,
            max_attempts=3,
            ingester=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("upstream detail")),
        )
        task = self.db.scalar(select(JobIngestionTask))
        self.assertEqual(task.status, "retry")
        self.assertEqual(task.attempts, 1)
        self.assertGreater(task.available_at, before.replace(tzinfo=None))
        self.assertEqual(task.last_error_code, "TimeoutError")
        self.assertIsNone(task.lease_token)

    def test_failure_retries_then_stops_without_persisting_exception_text(self):
        enqueue_ingestion_task(self.db, self.source.source_id, "pilot:failure", registry=self.registry)
        self.db.commit()
        result = process_one_task(
            self.db,
            "worker-test",
            registry=self.registry,
            max_attempts=1,
            ingester=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret response body")),
        )
        task = self.db.scalar(select(JobIngestionTask))
        self.assertIsNone(result)
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.last_error_code, "RuntimeError")
        self.assertNotIn("secret", task.last_error_code)
        self.assertIsNone(task.lease_token)


if __name__ == "__main__":
    unittest.main()
