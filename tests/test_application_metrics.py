import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.database import Base
from app.models import Application, ApplicationEvent, Job


class ApplicationMetricsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()

        job_a = Job(owner_id="owner-a", source="Gmail", external_id="a-1", company="Empresa A", title="Analista", location="Salvador", modality="hibrido", url="https://example.test/a", description="")
        job_b = Job(owner_id="owner-a", source="manual", external_id="a-2", company="Empresa B", title="Coordenador", location="Remoto", modality="remoto", url="https://example.test/b", description="")
        job_other = Job(owner_id="owner-b", source="Gmail", external_id="b-1", company="Empresa C", title="RH", location="Sao Paulo", modality="presencial", url="https://example.test/c", description="")
        db.add_all([job_a, job_b, job_other])
        db.flush()
        app_a = Application(job_id=job_a.id, status="ENTREVISTA", resume_version="cv-a1b2c3d4", cover_letter_version="carta-e5f6g7h8")
        app_b = Application(job_id=job_b.id, status="ANALISADA")
        app_other = Application(job_id=job_other.id, status="ENTREVISTA")
        db.add_all([app_a, app_b, app_other])
        db.flush()
        db.add_all([
            ApplicationEvent(application_id=app_a.id, status="IDENTIFICADA", note="capturada"),
            ApplicationEvent(application_id=app_a.id, status="CANDIDATURA_ENVIADA", note="enviada", channel="linkedin", resume_version="cv-a1b2c3d4", cover_letter_version="carta-e5f6g7h8"),
            ApplicationEvent(application_id=app_a.id, status="ENTREVISTA", note="entrevista confirmada", external_result="ENTREVISTA"),
            ApplicationEvent(application_id=app_b.id, status="IDENTIFICADA", note="capturada"),
            ApplicationEvent(application_id=app_other.id, status="CANDIDATURA_ENVIADA"),
            ApplicationEvent(application_id=app_other.id, status="ENTREVISTA"),
        ])
        db.commit()
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def test_metrics_are_owner_scoped_and_calculate_rate_per_100(self):
        with patch.object(main_module, "SessionLocal", self.session_factory):
            metrics = main_module.application_metrics({"id": "owner-a"})

        self.assertEqual(metrics["captured"], 2)
        self.assertEqual(metrics["submitted"], 1)
        self.assertEqual(metrics["qualified_interviews"], 1)
        self.assertEqual(metrics["interview_rate_per_100"], 100.0)
        self.assertEqual({item["source"] for item in metrics["by_source"]}, {"gmail", "manual"})
        gmail = next(item for item in metrics["by_source"] if item["source"] == "gmail")
        self.assertEqual(gmail["submitted"], 1)
        self.assertEqual(gmail["interviews"], 1)
        self.assertEqual(metrics["by_channel"], [{"channel": "linkedin", "submitted": 1, "interviews": 1, "interview_rate_per_100": 100.0, "sample_sufficient": False}])
        self.assertEqual(metrics["by_document_version"][0]["resume_version"], "cv-a1b2c3d4")
        self.assertEqual(metrics["by_document_version"][0]["cover_letter_version"], "carta-e5f6g7h8")


if __name__ == "__main__":
    unittest.main()
