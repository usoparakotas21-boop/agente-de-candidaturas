import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base
from app.models import BillingSubscription, utc_now


class EbookPlanEntitlementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_active_consultoria_subscription_can_download_the_book(self):
        db = self.session_factory()
        try:
            db.add(BillingSubscription(
                owner_id="consultoria-owner", plan_code="consultoria",
                external_reference="book-test-consultoria", payer_email="person@example.com",
                monthly_amount=19700, currency="BRL", status="authorized",
                access_until=utc_now() + timedelta(days=10),
            ))
            db.commit()
        finally:
            db.close()

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_document_export_metadata", return_value={"allowed": False, "plan": "essential"}),
        ):
            response = main_module.download_pro_ebook({"id": "consultoria-owner", "email": "person@example.com"})
        self.assertEqual(response.path, main_module.PRO_BOOK_PATH)
        self.assertEqual(response.media_type, "application/zip")

    def test_active_pro_subscription_can_download_the_book(self):
        db = self.session_factory()
        try:
            db.add(BillingSubscription(
                owner_id="pro-owner", plan_code="pro",
                external_reference="book-test-pro", payer_email="person@example.com",
                monthly_amount=9900, currency="BRL", status="authorized",
                access_until=utc_now() + timedelta(days=10),
            ))
            db.commit()
        finally:
            db.close()

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_document_export_metadata", return_value={"allowed": False, "plan": "essential"}),
        ):
            response = main_module.download_pro_ebook({"id": "pro-owner", "email": "person@example.com"})

        self.assertEqual(response.path, main_module.NORMAL_BOOK_PATH)
        self.assertTrue(main_module.NORMAL_BOOK_PATH.is_file())
        self.assertEqual(response.media_type, "application/pdf")

    def test_start_plan_or_no_active_entitlement_cannot_download_book(self):
        user = {"id": "start-owner", "email": "person@example.com"}
        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_document_export_metadata", return_value={"allowed": True, "plan": "start"}),
        ):
            with self.assertRaises(HTTPException) as denied:
                main_module.download_pro_ebook(user)
        self.assertEqual(denied.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
