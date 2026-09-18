import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.database import Base
from app.models import Application, ApplicationEvent, Job, utc_now


class FollowupsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        old = utc_now() - timedelta(days=9)
        job = Job(owner_id="owner-a", source="manual", external_id="follow-1", company="Empresa A", title="Analista", location="Salvador", modality="hibrido", url="https://example.test/1", description="Vaga")
        other = Job(owner_id="owner-b", source="manual", external_id="follow-2", company="Empresa B", title="Coordenador", location="Recife", modality="remoto", url="https://example.test/2", description="Vaga")
        db.add_all([job, other])
        db.flush()
        app = Application(job_id=job.id, status="CANDIDATURA_ENVIADA")
        other_app = Application(job_id=other.id, status="CANDIDATURA_ENVIADA")
        db.add_all([app, other_app])
        db.flush()
        db.add_all([
            ApplicationEvent(application_id=app.id, status="CANDIDATURA_ENVIADA", created_at=old),
            ApplicationEvent(application_id=other_app.id, status="CANDIDATURA_ENVIADA", created_at=old),
        ])
        db.commit()
        self.app_id = app.id
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def test_followup_is_owner_scoped_and_due_after_seven_days(self):
        with patch.object(main_module, "SessionLocal", self.session_factory):
            result = main_module.application_followups({"id": "owner-a"})

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["application_id"], self.app_id)
        self.assertGreaterEqual(result["items"][0]["days_waiting"], 9)
        self.assertIn("acompanhar", result["items"][0]["message"])


if __name__ == "__main__":
    unittest.main()
