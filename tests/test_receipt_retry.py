import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base
from app.models import DocumentExportPurchase, utc_now


class ReceiptRetryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.user = {
            "id": "receipt-owner",
            "email": "confirmed@example.com",
            "email_confirmed_at": "2026-09-22T00:00:00Z",
        }
        db = self.session_factory()
        db.add(DocumentExportPurchase(
            owner_id=self.user["id"],
            application_id=42,
            payer_email=self.user["email"],
            payer_email_confirmed=True,
            order_nsu="export-receipt-42",
            amount=990,
            paid_amount=990,
            status="PAID",
            transaction_nsu="payment-42",
            receipt_email_status="FAILED",
        ))
        db.commit()
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def test_retry_is_owner_scoped_and_returns_sent_status(self):
        def mark_sent(db, purchase):
            purchase.receipt_email_status = "SENT"
            purchase.receipt_email_sent_at = utc_now()
            db.commit()
            return "sent"

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module, "_send_purchase_receipt", side_effect=mark_sent) as send,
        ):
            result = main_module.retry_document_export_receipt(application_id=42, user=self.user)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["receipt_email_status"], "SENT")
        send.assert_called_once()

    def test_retry_rejects_unconfirmed_account_before_lookup(self):
        user = {"id": self.user["id"], "email": self.user["email"]}
        with patch.object(main_module, "SessionLocal") as session_local:
            with self.assertRaises(HTTPException) as raised:
                main_module.retry_document_export_receipt(application_id=42, user=user)
        self.assertEqual(raised.exception.status_code, 403)
        session_local.assert_not_called()

    def test_retry_cannot_access_another_owner_purchase(self):
        other = dict(self.user, id="other-owner")
        with patch.object(main_module, "SessionLocal", self.session_factory):
            with self.assertRaises(HTTPException) as raised:
                main_module.retry_document_export_receipt(application_id=42, user=other)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
