import unittest
from datetime import date, timedelta

from app.source_governance import (
    JobSource,
    SourceApprovalError,
    SourceRegistry,
    SourceStatus,
    SourceUse,
    require_approved_source,
)


def approved_source(source_id="pilot-board", domains=("jobs.example.com",), **overrides):
    values = {
        "source_id": source_id,
        "display_name": "Pilot board",
        "source_owner": "Example Hiring Ltd.",
        "source_owner_reference": "https://example.com/legal/company",
        "approved_domains": domains,
        "endpoint_url": f"https://{domains[0]}/api/v1/jobs",
        "allowed_fields": ("title", "company", "location", "description", "apply_url"),
        "permitted_uses": frozenset({SourceUse.AUTOMATED_FETCH}),
        "status": SourceStatus.APPROVED,
        "permission_basis": "Written permission from the source owner",
        "permission_evidence": "https://docs.example.com/permission/123",
        "terms_reference": "https://jobs.example.com/terms",
        "robots_review": "Reviewed 2026-09-20; automated collection permitted",
        "attribution": "Display source name and original listing link",
        "rate_limit_requests_per_minute": 12,
        "rate_limit_max_concurrency": 2,
        "raw_content_retention_ttl_days": 30,
        "reviewed_at": date(2026, 9, 20),
    }
    values.update(overrides)
    return JobSource(**values)


class SourceGovernanceTests(unittest.TestCase):
    def test_global_registry_is_empty_and_unknown_sources_fail_closed(self):
        empty = SourceRegistry()
        self.assertEqual(len(empty), 0)
        with self.assertRaises(SourceApprovalError):
            require_approved_source("linkedin")
        with self.assertRaises(SourceApprovalError):
            require_approved_source("https://jobs.example.com/api/v1/jobs", registry=empty)

    def test_pending_source_is_not_authorized(self):
        pending = approved_source(status=SourceStatus.PENDING)
        registry = SourceRegistry([pending])
        with self.assertRaisesRegex(SourceApprovalError, "not approved"):
            require_approved_source("https://jobs.example.com/api/v1/jobs", registry=registry)

    def test_complete_approved_source_resolves_by_exact_host_and_id(self):
        source = approved_source()
        registry = SourceRegistry([source])
        self.assertEqual(
            require_approved_source(
                "https://jobs.example.com/api/v1/jobs?ref=mail", registry=registry
            ),
            source,
        )
        self.assertEqual(require_approved_source("pilot-board", registry=registry), source)
        self.assertEqual(require_approved_source(source, registry=registry), source)

    def test_required_uses_are_checked_individually(self):
        source = approved_source()
        registry = SourceRegistry([source])
        for requested_use in (
            SourceUse.COMMERCIAL_DISPLAY,
            SourceUse.AI_PROCESSING,
            SourceUse.DESCRIPTION_CACHING,
            SourceUse.REDISTRIBUTION,
        ):
            with self.subTest(requested_use=requested_use), self.assertRaisesRegex(
                SourceApprovalError, "does not grant required uses"
            ):
                require_approved_source(
                    "pilot-board", registry=registry, required_uses=(requested_use,)
                )

        licensed = approved_source(permitted_uses=frozenset(SourceUse))
        licensed_registry = SourceRegistry([licensed])
        self.assertEqual(
            require_approved_source(
                "pilot-board",
                registry=licensed_registry,
                required_uses=(SourceUse.AI_PROCESSING, SourceUse.COMMERCIAL_DISPLAY),
            ),
            licensed,
        )

    def test_approved_source_requires_structured_owner_endpoint_fields_and_fetch_right(self):
        source = approved_source(
            source_owner="",
            source_owner_reference="",
            endpoint_url="",
            allowed_fields=(),
            permitted_uses=frozenset(),
        )
        registry = SourceRegistry([source])
        with self.assertRaisesRegex(
            SourceApprovalError,
            "source_owner, source_owner_reference, endpoint_url, allowed_fields, permitted_uses",
        ):
            require_approved_source("pilot-board", registry=registry)

    def test_approved_status_without_other_evidence_still_fails(self):
        source = approved_source(permission_evidence="", robots_review="")
        registry = SourceRegistry([source])
        with self.assertRaisesRegex(SourceApprovalError, "permission_evidence, robots_review"):
            require_approved_source("pilot-board", registry=registry)

    def test_url_must_match_exact_reviewed_endpoint_path(self):
        registry = SourceRegistry([approved_source()])
        with self.assertRaisesRegex(SourceApprovalError, "does not match the reviewed endpoint"):
            require_approved_source("https://jobs.example.com/api/v1/other", registry=registry)

    def test_approvals_expire_after_180_days_and_future_reviews_fail(self):
        source = approved_source()
        registry = SourceRegistry([source])
        exactly_180_days = source.reviewed_at + timedelta(days=180)
        self.assertEqual(
            require_approved_source("pilot-board", registry=registry, as_of=exactly_180_days),
            source,
        )
        with self.assertRaisesRegex(SourceApprovalError, "approval is stale"):
            require_approved_source(
                "pilot-board", registry=registry, as_of=source.reviewed_at + timedelta(days=181)
            )
        with self.assertRaisesRegex(SourceApprovalError, "future review date"):
            require_approved_source(
                "pilot-board", registry=registry, as_of=source.reviewed_at - timedelta(days=1)
            )

    def test_forged_lookalikes_and_unlisted_subdomains_do_not_match(self):
        source = approved_source(domains=("gupy.com.br",))
        registry = SourceRegistry([source])
        for url in (
            "https://gupy.com.br.attacker.test/api/v1/jobs",
            "https://gupy.com.br.evil.example/api/v1/jobs",
            "https://fakegupy.com.br/api/v1/jobs",
            "https://careers.gupy.com.br/api/v1/jobs",
        ):
            with self.subTest(url=url), self.assertRaises(SourceApprovalError):
                require_approved_source(url, registry=registry)

    def test_subdomain_must_be_listed_and_selected_as_endpoint_explicitly(self):
        source = approved_source(
            domains=("gupy.com.br", "careers.gupy.com.br"),
            endpoint_url="https://careers.gupy.com.br/api/v1/jobs",
        )
        registry = SourceRegistry([source])
        self.assertEqual(
            require_approved_source("https://careers.gupy.com.br/api/v1/jobs", registry=registry),
            source,
        )

    def test_invalid_or_ambiguous_urls_are_rejected(self):
        registry = SourceRegistry([approved_source()])
        invalid_urls = (
            "jobs.example.com/api/v1/jobs",  # missing scheme
            "http://jobs.example.com/api/v1/jobs",  # TLS required
            "ftp://jobs.example.com/api/v1/jobs",
            "https://user:password@jobs.example.com/api/v1/jobs",
            "https://jobs.example.com:444/api/v1/jobs",
            "https://jobs.example.com:notaport/api/v1/jobs",
            "https://jobs.example.com./api/v1/jobs",  # trailing-dot ambiguity
            "https://jobs.example.com/api/v1/jobs#section",
            "https://jobs.example.com\\@attacker.test/api/v1/jobs",
            "//jobs.example.com/api/v1/jobs",
            "https://localhost/api/v1/jobs",
            "https://127.0.0.1/api/v1/jobs",
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(SourceApprovalError):
                require_approved_source(url, registry=registry)

    def test_overlapping_source_records_fail_as_ambiguous(self):
        registry = SourceRegistry(
            [
                approved_source(source_id="board-one"),
                approved_source(source_id="board-two"),
            ]
        )
        with self.assertRaisesRegex(SourceApprovalError, "multiple source records"):
            require_approved_source(
                "https://jobs.example.com/api/v1/jobs", registry=registry
            )

    def test_bad_registry_domains_and_rate_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            approved_source(domains=("https://jobs.example.com",))
        with self.assertRaises(ValueError):
            approved_source(domains=("jobs.example.com.evil.test/path",))
        with self.assertRaises(ValueError):
            approved_source(rate_limit_requests_per_minute=0)
        with self.assertRaises(ValueError):
            approved_source(rate_limit_requests_per_minute=1.5)
        with self.assertRaises(ValueError):
            approved_source(rate_limit_max_concurrency=0)
        with self.assertRaises(ValueError):
            approved_source(raw_content_retention_ttl_days=-1)
        with self.assertRaises(ValueError):
            approved_source(endpoint_url="https://unlisted.example.net/api/jobs")
        with self.assertRaises(ValueError):
            approved_source(endpoint_url="https://jobs.example.com/api/jobs?scope=all")


if __name__ == "__main__":
    unittest.main()
