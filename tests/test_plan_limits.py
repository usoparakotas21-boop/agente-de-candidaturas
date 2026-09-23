import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Application, BillingSubscription, Job, QueueItem
from app.plan_limits import (
    PlanLimitReachedError,
    ensure_opportunity_capacity,
    month_window,
    monthly_opportunity_usage,
)
from app.queue_service import enqueue


class PlanLimitTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.session_factory()
        self.now = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _queue_item(self, owner_id, index, captured_at=None, job_id=None):
        self.db.add(
            QueueItem(
                owner_id=owner_id,
                source="gmail",
                decision="REVISAR",
                decision_engine_version="test",
                dedup_hash=f"{index:064x}",
                captured_at=captured_at or self.now,
                job_id=job_id,
            )
        )

    def _subscription(self, owner_id, plan):
        self.db.add(
            BillingSubscription(
                owner_id=owner_id,
                plan_code=plan,
                external_reference=f"subscription-{owner_id}-{plan}",
                payer_email="candidate@example.com",
                monthly_amount=3490 if plan == "start" else 9900,
                status="authorized",
                access_until=self.now + timedelta(days=10),
            )
        )

    def test_free_plan_has_thirty_monthly_opportunities_and_blocks_the_next(self):
        for index in range(50):
            self._queue_item("free-user", index)
        self.db.commit()

        usage = monthly_opportunity_usage(self.db, "free-user", self.now)
        self.assertEqual((usage["plan_code"], usage["used"], usage["limit"]), ("essential", 50, 50))
        with self.assertRaises(PlanLimitReachedError):
            ensure_opportunity_capacity(self.db, "free-user", self.now)

    def test_queue_limit_blocks_new_items_but_does_not_consume_duplicates(self):
        for index in range(50):
            self._queue_item("queue-user", index)
        self.db.commit()
        duplicate, created = enqueue(
            self.db,
            "queue-user",
            {"dedup_hash": f"{0:064x}", "title": "Analista", "company": "Empresa"},
            {"decision": "REVISAR", "decision_engine_version": "test"},
            "gmail",
        )
        self.assertFalse(created)
        self.assertEqual(duplicate.seen_count, 2)
        with self.assertRaises(PlanLimitReachedError):
            enqueue(
                self.db,
                "queue-user",
                {"dedup_hash": "f" * 64, "title": "Outra vaga", "company": "Outra empresa"},
                {"decision": "REVISAR", "decision_engine_version": "test"},
                "gmail",
            )

    def test_start_and_pro_have_distinct_limits_only_while_entitled(self):
        self._subscription("start-user", "start")
        self._subscription("pro-user", "pro")
        self.db.commit()

        start = monthly_opportunity_usage(self.db, "start-user", self.now)
        pro = monthly_opportunity_usage(self.db, "pro-user", self.now)
        self.assertEqual((start["plan_code"], start["limit"]), ("start", 250))
        self.assertEqual((pro["plan_code"], pro["limit"]), ("pro", 1000))

        expired_at = self.now - timedelta(seconds=1)
        start_subscription = self.db.query(BillingSubscription).filter_by(owner_id="start-user").one()
        start_subscription.access_until = expired_at
        self.db.commit()
        self.assertEqual(monthly_opportunity_usage(self.db, "start-user", self.now)["plan_code"], "essential")

    def test_month_resets_at_midnight_in_brazil(self):
        before_midnight = datetime(2026, 10, 1, 2, 59, tzinfo=timezone.utc)
        after_midnight = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)
        _, september_end = month_window(before_midnight)
        october_start, _ = month_window(after_midnight)
        self.assertEqual(september_end, october_start)
        self.assertEqual(october_start, after_midnight)

    def test_direct_job_and_captured_queue_are_counted_once(self):
        job = Job(
            owner_id="direct-user",
            source="manual",
            external_id="direct-1",
            company="Empresa",
            title="Analista",
            location="",
            modality="",
            url="",
            description="Descrição da vaga",
        )
        self.db.add(job)
        self.db.flush()
        self.db.add(Application(job_id=job.id, status="IDENTIFICADA"))
        self._queue_item("direct-user", 1, job_id=job.id)
        self.db.commit()
        self.assertEqual(monthly_opportunity_usage(self.db, "direct-user", self.now)["used"], 1)


if __name__ == "__main__":
    unittest.main()
