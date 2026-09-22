import json
import unittest
from datetime import date
from unittest.mock import Mock

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.job_ingestion import (
    JobIngestionError,
    fetch_authorized_json_feed,
    normalize_job_listing,
    upsert_job_listings,
)
from app.models import JobListing
from app.source_governance import (
    JobSource,
    SourceApprovalError,
    SourceRegistry,
    SourceStatus,
    SourceUse,
)


def make_source(**overrides):
    values = {
        "source_id": "pilot-board",
        "display_name": "Pilot board",
        "source_owner": "Example Hiring Ltd.",
        "source_owner_reference": "https://example.com/legal/company",
        "approved_domains": ("jobs.example.com",),
        "endpoint_url": "https://jobs.example.com/api/v1/jobs",
        "allowed_fields": (
            "external_id", "title", "company", "location", "description",
            "apply_url", "salary_range", "work_mode", "contract_type", "status",
        ),
        "permitted_uses": frozenset({
            SourceUse.AUTOMATED_FETCH,
            SourceUse.COMMERCIAL_DISPLAY,
            SourceUse.DESCRIPTION_CACHING,
        }),
        "status": SourceStatus.APPROVED,
        "permission_basis": "Written permission from source owner",
        "permission_evidence": "https://docs.example.com/permission/123",
        "terms_reference": "https://jobs.example.com/terms",
        "robots_review": "Reviewed 2026-09-20; automated JSON feed permitted",
        "attribution": "Show source name and original listing link",
        "rate_limit_requests_per_minute": 12,
        "rate_limit_max_concurrency": 2,
        "raw_content_retention_ttl_days": 30,
        "reviewed_at": date.today(),
    }
    values.update(overrides)
    return JobSource(**values)


class FakeResponse:
    def __init__(self, body, *, status_code=200, content_type="application/json"):
        self.status_code = status_code
        self.headers = {"content-type": content_type, "content-length": str(len(body))}
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("unexpected HTTP status")

    def iter_bytes(self):
        yield self._body


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def stream(self, method, url):
        self.request = (method, url)
        return self.response


class JobIngestionTests(unittest.TestCase):
    def setUp(self):
        self.source = make_source()
        self.registry = SourceRegistry([self.source])

    def test_normalizes_portuguese_text_and_removes_unsafe_markup(self):
        result = normalize_job_listing(
            {
                "external_id": "vaga-123",
                "title": "Analista de Dados Remoto",
                "company": "<b>Empresa Exemplo</b>",
                "location": "Salvador/BA",
                "description": "<p>Vaga CLT em trabalho remoto.</p><script>alert(1)</script>",
                "apply_url": "https://careers.example.com/apply/123",
                "salary_range": "R$ 8.000 a R$ 10.000",
            },
            self.source,
        )
        self.assertEqual(result["work_mode"], "remote")
        self.assertEqual(result["contract_type"], "CLT")
        self.assertEqual(result["company_name"], "Empresa Exemplo")
        self.assertNotIn("alert(1)", result["description"])

    def test_ambiguous_classification_stays_unknown(self):
        result = normalize_job_listing(
            {
                "external_id": "vaga-124",
                "title": "Analista",
                "description": "Pode ser remoto ou presencial, contrato CLT ou PJ.",
                "apply_url": "https://careers.example.com/apply/124",
            },
            self.source,
        )
        self.assertIsNone(result["work_mode"])
        self.assertIsNone(result["contract_type"])

    def test_unknown_source_fails_before_network_or_rate_limiter(self):
        factory = Mock(side_effect=AssertionError("network must not be reached"))
        limiter = Mock(side_effect=AssertionError("rate limiter should not be reached"))
        with self.assertRaises(SourceApprovalError):
            fetch_authorized_json_feed(
                "linkedin",
                registry=SourceRegistry(),
                client_factory=factory,
                limiter_is_configured=lambda: True,
                limiter_check=limiter,
            )
        factory.assert_not_called()
        limiter.assert_not_called()

    def test_feed_fetch_uses_fixed_endpoint_and_distributed_rate_limit(self):
        body = json.dumps({"jobs": [{"title": "Analista", "apply_url": "https://careers.example.com/1"}]}).encode()
        client = FakeClient(FakeResponse(body))
        factory = Mock(return_value=client)
        limiter = Mock(return_value=(False, 0))
        records = fetch_authorized_json_feed(
            self.source.source_id,
            registry=self.registry,
            client_factory=factory,
            limiter_is_configured=lambda: True,
            limiter_check=limiter,
            lease_acquire=lambda _key, _ttl: "lease-token",
            lease_release=lambda _key, _token: True,
        )
        self.assertEqual(records[0]["title"], "Analista")
        self.assertEqual(client.request, ("GET", self.source.endpoint_url))
        limiter.assert_called_once_with(["job-ingestion:pilot-board"], 12, 60)

    def test_redirect_is_rejected_without_following_it(self):
        client = FakeClient(FakeResponse(b"", status_code=302))
        with self.assertRaisesRegex(JobIngestionError, "redirects"):
            fetch_authorized_json_feed(
                self.source.source_id,
                registry=self.registry,
                client_factory=lambda **_kwargs: client,
                limiter_is_configured=lambda: True,
                limiter_check=lambda *_args: (False, 0),
                lease_acquire=lambda _key, _ttl: "lease-token",
                lease_release=lambda _key, _token: True,
            )

    def test_description_cache_right_is_required_before_fetch(self):
        source = make_source(permitted_uses=frozenset({
            SourceUse.AUTOMATED_FETCH,
            SourceUse.COMMERCIAL_DISPLAY,
        }))
        registry = SourceRegistry([source])
        factory = Mock(side_effect=AssertionError("network must not be reached"))
        with self.assertRaisesRegex(SourceApprovalError, "description_caching"):
            fetch_authorized_json_feed(
                source.source_id,
                registry=registry,
                client_factory=factory,
                limiter_is_configured=lambda: True,
            )
        factory.assert_not_called()

    def test_upsert_deduplicates_by_source_and_external_id_and_refreshes_fields(self):
        engine = create_engine("sqlite://")
        JobListing.__table__.create(engine)
        try:
            with Session(engine) as db:
                first = upsert_job_listings(
                    db,
                    self.source.source_id,
                    [{"external_id": "same", "title": "Analista", "apply_url": "https://careers.example.com/1"}],
                    registry=self.registry,
                )
                db.commit()
                second = upsert_job_listings(
                    db,
                    self.source.source_id,
                    [{"external_id": "same", "title": "Analista Sênior", "apply_url": "https://careers.example.com/1"}],
                    registry=self.registry,
                )
                db.commit()
                row = db.execute(select(JobListing)).scalar_one()
                count = db.execute(select(func.count()).select_from(JobListing)).scalar_one()
            self.assertEqual(first.upserted, 1)
            self.assertEqual(second.upserted, 1)
            self.assertEqual(count, 1)
            self.assertEqual(row.title, "Analista Sênior")
        finally:
            engine.dispose()

    def test_invalid_listing_is_skipped_and_bad_urls_are_not_stored(self):
        engine = create_engine("sqlite://")
        JobListing.__table__.create(engine)
        try:
            with Session(engine) as db:
                result = upsert_job_listings(
                    db,
                    self.source.source_id,
                    [
                        {"external_id": "bad", "title": "Analista", "apply_url": "http://careers.example.com/1"},
                        {"external_id": "good", "title": "Analista", "apply_url": "https://careers.example.com/2"},
                    ],
                    registry=self.registry,
                )
                db.commit()
            self.assertEqual((result.fetched, result.upserted, result.skipped), (2, 1, 1))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
