import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app.source_authorization import (
    check_source_record,
    load_authorized_sources_from_environment,
    load_authorized_sources_from_json,
    load_source_record,
    source_to_record,
)
from app.source_governance import SourceRegistry


def complete_record(**overrides):
    record = {
        "source_id": "pilot-board",
        "display_name": "Pilot board",
        "source_owner": "Example Hiring Ltd.",
        "source_owner_reference": "https://example.com/legal/company",
        "approved_domains": ["jobs.example.com"],
        "endpoint_url": "https://jobs.example.com/api/v1/jobs",
        "allowed_fields": ["title", "company", "location", "apply_url"],
        "permitted_uses": ["automated_fetch", "commercial_display"],
        "status": "approved",
        "permission_basis": "Written permission from the source owner",
        "permission_evidence": "https://docs.example.com/permission/123",
        "terms_reference": "https://jobs.example.com/terms",
        "robots_review": "Reviewed 2026-09-20; automated collection permitted",
        "attribution": "Display source name and original listing link",
        "rate_limit_requests_per_minute": 12,
        "rate_limit_max_concurrency": 2,
        "raw_content_retention_ttl_days": 30,
        "reviewed_at": "2026-09-20",
    }
    record.update(overrides)
    return record


class SourceAuthorizationTests(unittest.TestCase):
    def test_incomplete_record_reports_schema_errors_without_activation(self):
        result = check_source_record({"source_id": "draft"})
        self.assertFalse(result.schema_valid)
        self.assertFalse(result.ready_for_registration)
        self.assertIn("missing fields", result.errors[0])

    def test_pending_record_is_valid_but_not_ready(self):
        result = check_source_record(
            complete_record(status="pending"), as_of=date(2026, 9, 22)
        )
        self.assertTrue(result.schema_valid)
        self.assertFalse(result.ready_for_registration)
        self.assertIn("not approved", result.approval_error)

    def test_complete_record_is_ready_but_not_registered(self):
        result = check_source_record(complete_record(), as_of=date(2026, 9, 22))
        self.assertTrue(result.schema_valid)
        self.assertTrue(result.ready_for_registration)
        self.assertEqual(result.approval_gaps, ())

    def test_unknown_keys_and_bad_json_are_rejected(self):
        result = check_source_record(complete_record(extra="must fail"))
        self.assertFalse(result.schema_valid)
        self.assertIn("unknown fields", result.errors[0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                load_source_record(path)

    def test_round_trip_keeps_explicit_rights_and_never_adds_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_text(json.dumps(complete_record()), encoding="utf-8")
            source = load_source_record(path)
        serialized = source_to_record(source)
        self.assertEqual(
            set(serialized["permitted_uses"]),
            {"automated_fetch", "commercial_display"},
        )
        self.assertNotIn("automated_submission", serialized["permitted_uses"])

    def test_environment_payload_registers_approved_sources_atomically(self):
        registry = SourceRegistry()
        loaded = load_authorized_sources_from_json(
            json.dumps([complete_record()]),
            registry=registry,
            as_of=date(2026, 9, 22),
        )
        self.assertEqual([source.source_id for source in loaded], ["pilot-board"])
        self.assertEqual([source.source_id for source in registry.sources()], ["pilot-board"])

    def test_pending_record_does_not_partially_activate_environment_payload(self):
        registry = SourceRegistry()
        payload = json.dumps([
            complete_record(source_id="approved-board"),
            complete_record(source_id="pending-board", status="pending"),
        ])
        with self.assertRaisesRegex(ValueError, "pending-board is not ready"):
            load_authorized_sources_from_json(
                payload,
                registry=registry,
                as_of=date(2026, 9, 22),
            )
        self.assertEqual(registry.sources(), ())

    def test_empty_environment_keeps_registry_empty(self):
        registry = SourceRegistry()
        with mock.patch.dict("os.environ", {"SOURCE_AUTHORIZATION_RECORDS_JSON": ""}):
            self.assertEqual(load_authorized_sources_from_environment(registry=registry), ())


if __name__ == "__main__":
    unittest.main()
