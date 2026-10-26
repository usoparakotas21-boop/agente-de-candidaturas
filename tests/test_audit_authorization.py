import asyncio
import os
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import auth, main
from app.database import Base
from app.models import BillingSubscription, Candidate, utc_now
from app.plan_limits import _effective_plan, ensure_opportunity_capacity


class AuditAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_profile_email_cannot_steal_subscription_or_admin_quota(self):
        with self.sessions() as db:
            db.add(Candidate(owner_id="attacker", name="Test", location="", phone="", linkedin="", target_roles="", summary="", email="contato@candidaturacerta.com.br"))
            db.add(BillingSubscription(
                owner_id="victim", payer_email="contato@candidaturacerta.com.br",
                plan_code="consultoria", external_reference="audit-victim", status="authorized",
                monthly_amount=19700, currency="BRL", access_until=utc_now() + timedelta(days=10),
            ))
            db.commit()
            self.assertEqual(_effective_plan(db, "attacker", utc_now()), "essential")
            self.assertEqual(ensure_opportunity_capacity(db, "attacker")["limit"], 50)
            self.assertEqual(_effective_plan(db, "victim", utc_now()), "consultoria")

    def test_entitlement_lookup_does_not_follow_other_candidates_email(self):
        with self.sessions() as db:
            db.add(Candidate(owner_id="victim", name="Test", location="", phone="", linkedin="", target_roles="", summary="", email="person@example.com"))
            db.add(BillingSubscription(
                owner_id="victim", payer_email="person@example.com", plan_code="pro",
                external_reference="audit-sub", status="authorized", monthly_amount=9900,
                currency="BRL", access_until=utc_now() + timedelta(days=10),
            ))
            db.commit()
        with patch.object(main, "SessionLocal", self.sessions):
            self.assertFalse(main._get_user_plan_and_entitlement(
                {"id": "attacker", "email": "person@example.com"}
            )["entitled"])
            self.assertTrue(main._get_user_plan_and_entitlement(
                {"id": "victim", "email": "person@example.com"}
            )["entitled"])

    def test_debug_values_never_grant_admin(self):
        request = Request({"type": "http", "headers": []})
        for debug in ("true", "false", "1"):
            with self.subTest(debug=debug), patch.dict(os.environ, {"DEBUG": debug}), patch.object(
                auth, "_resolve_session", new=AsyncMock(return_value=({"id": "ordinary", "email": "ordinary@example.com"}, None))
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(main._require_admin(request))
                self.assertEqual(caught.exception.status_code, 403)

    def test_quota_and_entitlement_agree_on_paid_period(self):
        for status in ("active", "authorized", "paused", "canceled", "pending", "suspended", "superseded", "rejected"):
            for period in (None, -1, 1):
                with self.subTest(status=status, period=period), self.sessions() as db:
                    db.query(BillingSubscription).delete()
                    db.add(BillingSubscription(
                        owner_id="owner", payer_email="person@example.com", plan_code="pro",
                        external_reference="audit-period", status=status, monthly_amount=9900,
                        currency="BRL", access_until=None if period is None else utc_now() + timedelta(days=period),
                    ))
                    db.commit()
                    with patch.object(main, "SessionLocal", self.sessions):
                        entitlement = main._get_user_plan_and_entitlement(
                            {"id": "owner", "email": "person@example.com"}
                        )
                    expected = period == 1 and status not in {"suspended", "superseded", "rejected"}
                    self.assertEqual(entitlement["entitled"], expected)
                    self.assertEqual(_effective_plan(db, "owner", utc_now()), "pro" if expected else "essential")

    def test_admin_cannot_skip_verified_email_or_mfa(self):
        request = Request({"type": "http", "headers": []})
        user = {"id": "admin", "email": "contato@candidaturacerta.com.br", "email_confirmed_at": None}
        with patch.object(auth, "_resolve_session", new=AsyncMock(return_value=(user, None))):
            with self.assertRaises(HTTPException):
                asyncio.run(main._require_admin(request))
        user["email_confirmed_at"] = "2026-10-01"
        with patch.object(auth, "_resolve_session", new=AsyncMock(return_value=(user, None))), patch.object(
            auth, "_session_requires_mfa", return_value=True
        ):
            with self.assertRaises(HTTPException):
                asyncio.run(main._require_admin(request))


    def test_superseded_record_never_hides_a_valid_active_subscription(self):
        with self.sessions() as db:
            db.add(BillingSubscription(owner_id="owner", payer_email="owner@example.com", plan_code="pro", external_reference="paid", status="authorized", monthly_amount=9900, currency="BRL", access_until=utc_now()+timedelta(days=10)))
            db.flush()
            db.add(BillingSubscription(owner_id="owner", payer_email="owner@example.com", plan_code="start", external_reference="old-courtesy", status="superseded", monthly_amount=0, currency="BRL", access_until=utc_now()+timedelta(days=15)))
            db.commit()
            self.assertEqual(_effective_plan(db, "owner", utc_now()), "pro")

    def test_courtesy_account_does_not_gain_admin_authority(self):
        user = {"id": "courtesy-owner", "email": "henriqueoliveirarh93@gmail.com", "email_confirmed_at": "2026-10-01"}
        self.assertFalse(main.is_admin(user))
        entitlement = main._get_user_plan_and_entitlement(user)
        self.assertTrue(entitlement["entitled"])
        self.assertFalse(entitlement["is_admin"])

    def test_admin_requires_verified_identity_and_trusted_metadata(self):
        user = {"id": "ordinary", "email": "ordinary@example.com", "email_confirmed_at": "2026-10-01", "user_metadata": {"is_admin": True}}
        self.assertFalse(main.is_admin(user))
        user["app_metadata"] = {"is_admin": "false"}
        self.assertFalse(main.is_admin(user))
        user["app_metadata"] = {"is_admin": True}
        self.assertTrue(main.is_admin(user))
        user["email_confirmed_at"] = None
        self.assertFalse(main.is_admin(user))



if __name__ == "__main__":
    unittest.main()
